import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getSettings } from "@/lib/content";
import { createPayment, isPaymentsConfigured } from "@/lib/yookassa";

export async function POST(req: Request) {
  let data: Record<string, unknown>;
  try {
    data = await req.json();
  } catch {
    return NextResponse.json({ error: "Некорректный запрос" }, { status: 400 });
  }

  const name = String(data.name ?? "").trim();
  const phone = String(data.phone ?? "").trim();
  const email = String(data.email ?? "").trim();
  const preferredDate = String(data.preferredDate ?? "").trim();
  const comment = String(data.comment ?? "").trim();
  const serviceSlug = data.serviceSlug ? String(data.serviceSlug) : "";
  const pay = Boolean(data.pay);

  if (!name || !phone) {
    return NextResponse.json({ error: "Укажите имя и телефон" }, { status: 400 });
  }

  const service = serviceSlug
    ? await prisma.service.findUnique({ where: { slug: serviceSlug } })
    : null;

  const order = await prisma.order.create({
    data: {
      serviceId: service?.id ?? null,
      serviceTitle: service?.title ?? "Консультация",
      customerName: name,
      customerPhone: phone,
      customerEmail: email,
      preferredDate,
      comment,
      amount: service?.price ?? 0,
      status: "new",
    },
  });

  // Optionally start an online payment via the cash register.
  if (pay && service && service.price > 0) {
    const settings = await getSettings();
    if (!isPaymentsConfigured(settings)) {
      return NextResponse.json({
        orderId: order.id,
        paid: false,
        message:
          "Заявка принята. Онлайн-оплата временно недоступна — мы свяжемся с вами для подтверждения.",
      });
    }
    try {
      const base = process.env.NEXT_PUBLIC_BASE_URL || new URL(req.url).origin;
      const payment = await createPayment(settings, {
        amount: service.price,
        description: `Оплата услуги: ${service.title}`,
        returnUrl: `${base}/booking/success?order=${order.id}`,
        customerEmail: email,
        customerPhone: phone,
        metadata: { orderId: order.id },
      });
      await prisma.order.update({
        where: { id: order.id },
        data: {
          paymentId: payment.id,
          paymentStatus: payment.status,
          paymentUrl: payment.confirmation?.confirmation_url ?? null,
          receiptStatus: settings.fiscalEnabled ? "pending" : "none",
        },
      });
      return NextResponse.json({
        orderId: order.id,
        paymentUrl: payment.confirmation?.confirmation_url ?? null,
      });
    } catch (e) {
      console.error("Payment creation failed", e);
      return NextResponse.json({
        orderId: order.id,
        paid: false,
        message:
          "Заявка принята, но онлайн-оплату начать не удалось. Мы свяжемся с вами для подтверждения.",
      });
    }
  }

  return NextResponse.json({ orderId: order.id });
}
