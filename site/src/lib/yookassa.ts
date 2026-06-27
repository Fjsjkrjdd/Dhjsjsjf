import "server-only";
import { randomUUID } from "crypto";
import type { SiteSettings } from "@prisma/client";

const API_URL = "https://api.yookassa.ru/v3";

export type CreatePaymentArgs = {
  amount: number;
  description: string;
  returnUrl: string;
  customerEmail?: string;
  customerPhone?: string;
  metadata?: Record<string, string>;
};

export type YooPayment = {
  id: string;
  status: string;
  confirmation?: { confirmation_url?: string };
  paid: boolean;
};

/** Whether the cash register is configured and ready to accept payments. */
export function isPaymentsConfigured(s: SiteSettings): boolean {
  const shopId = s.yooKassaShopId || process.env.YOOKASSA_SHOP_ID || "";
  const secret = s.yooKassaSecretKey || process.env.YOOKASSA_SECRET_KEY || "";
  return Boolean(s.paymentsEnabled && shopId && secret);
}

function authHeader(s: SiteSettings): string {
  const shopId = s.yooKassaShopId || process.env.YOOKASSA_SHOP_ID || "";
  const secret = s.yooKassaSecretKey || process.env.YOOKASSA_SECRET_KEY || "";
  return "Basic " + Buffer.from(`${shopId}:${secret}`).toString("base64");
}

/**
 * Build a 54-ФЗ fiscal receipt (чек) object for the online cash register.
 * Only included when fiscalization is enabled in settings.
 */
function buildReceipt(s: SiteSettings, args: CreatePaymentArgs) {
  if (!s.fiscalEnabled) return undefined;
  const customer: Record<string, string> = {};
  if (args.customerEmail) customer.email = args.customerEmail;
  if (args.customerPhone) customer.phone = args.customerPhone.replace(/[^0-9+]/g, "");
  if (!customer.email && !customer.phone) return undefined;

  return {
    customer,
    tax_system_code: s.taxSystemCode,
    items: [
      {
        description: args.description.slice(0, 128),
        quantity: "1.00",
        amount: { value: args.amount.toFixed(2), currency: "RUB" },
        vat_code: s.vatCode,
        payment_subject: s.paymentSubject,
        payment_mode: s.paymentMode,
      },
    ],
  };
}

/** Create a payment in YooKassa and return the payment with a confirmation URL. */
export async function createPayment(s: SiteSettings, args: CreatePaymentArgs): Promise<YooPayment> {
  const body = {
    amount: { value: args.amount.toFixed(2), currency: "RUB" },
    capture: true,
    confirmation: { type: "redirect", return_url: args.returnUrl },
    description: args.description.slice(0, 128),
    metadata: args.metadata,
    receipt: buildReceipt(s, args),
  };

  const res = await fetch(`${API_URL}/payments`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotence-Key": randomUUID(),
      Authorization: authHeader(s),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`YooKassa error ${res.status}: ${text}`);
  }
  return (await res.json()) as YooPayment;
}

/** Fetch a payment's current status from YooKassa. */
export async function getPayment(s: SiteSettings, paymentId: string): Promise<YooPayment> {
  const res = await fetch(`${API_URL}/payments/${paymentId}`, {
    headers: { Authorization: authHeader(s) },
  });
  if (!res.ok) throw new Error(`YooKassa error ${res.status}`);
  return (await res.json()) as YooPayment;
}
