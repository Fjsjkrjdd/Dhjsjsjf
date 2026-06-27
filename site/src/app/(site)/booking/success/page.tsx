import Link from "next/link";
import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { getSettings } from "@/lib/content";
import { getPayment, isPaymentsConfigured } from "@/lib/yookassa";
import { CheckIcon } from "@/components/icons";

export const metadata: Metadata = { title: "Оплата" };

type SearchParams = Promise<{ order?: string }>;

export default async function SuccessPage({ searchParams }: { searchParams: SearchParams }) {
  const { order: orderId } = await searchParams;
  let paid = false;

  if (orderId) {
    const order = await prisma.order.findUnique({ where: { id: orderId } });
    const settings = await getSettings();
    if (order?.paymentId && isPaymentsConfigured(settings)) {
      try {
        const payment = await getPayment(settings, order.paymentId);
        paid = payment.status === "succeeded" || payment.paid;
        await prisma.order.update({
          where: { id: order.id },
          data: {
            paymentStatus: payment.status,
            status: paid ? "paid" : order.status,
            receiptStatus: paid && order.receiptStatus === "pending" ? "registered" : order.receiptStatus,
          },
        });
      } catch {
        /* ignore */
      }
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-24 text-center sm:px-6">
      <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-sage text-white">
        <CheckIcon className="h-8 w-8" />
      </div>
      <h1 className="mt-6 text-3xl text-ink">
        {paid ? "Оплата прошла успешно" : "Спасибо за заявку!"}
      </h1>
      <p className="mt-4 text-ink-soft">
        {paid
          ? "Ваша оплата получена, чек отправлен на указанный e-mail. Я свяжусь с вами для подтверждения времени встречи."
          : "Заявка принята. Я свяжусь с вами в ближайшее время для подтверждения записи."}
      </p>
      <Link
        href="/"
        className="mt-8 inline-flex rounded-full bg-sage px-7 py-3 text-sm font-semibold text-white transition hover:bg-sage-dark"
      >
        Вернуться на главную
      </Link>
    </div>
  );
}
