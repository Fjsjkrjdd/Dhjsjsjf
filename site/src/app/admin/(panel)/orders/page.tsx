import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { formatPrice } from "@/lib/content";
import { updateOrderStatus, deleteOrder } from "../../_actions/cms";
import { PageHeader, Card, fieldClass } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Заявки и оплаты" };

const STATUS_LABEL: Record<string, string> = {
  new: "Новая",
  confirmed: "Подтверждена",
  paid: "Оплачена",
  cancelled: "Отменена",
  completed: "Завершена",
};

const PAY_LABEL: Record<string, string> = {
  pending: "Ожидает",
  waiting_for_capture: "Холдирование",
  succeeded: "Оплачено",
  canceled: "Отменено",
};

function fmt(d: Date) {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export default async function OrdersAdmin() {
  const orders = await prisma.order.findMany({ orderBy: { createdAt: "desc" } });

  return (
    <div>
      <PageHeader title="Заявки и оплаты" description="Заявки с сайта и статусы онлайн-оплат." />

      <div className="space-y-3">
        {orders.map((o) => (
          <Card key={o.id}>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-ink">{o.customerName}</span>
                  <span className="text-sm text-ink-soft">· {o.customerPhone}</span>
                  {o.customerEmail ? <span className="text-sm text-ink-soft">· {o.customerEmail}</span> : null}
                </div>
                <p className="mt-1 text-sm text-ink-soft">
                  {o.serviceTitle}
                  {o.amount > 0 ? ` · ${formatPrice(o.amount)} ₽` : ""}
                  {o.preferredDate ? ` · ${o.preferredDate}` : ""}
                </p>
                {o.comment ? <p className="mt-1 text-sm text-ink-soft">«{o.comment}»</p> : null}
                <p className="mt-1 text-xs text-ink-soft">{fmt(o.createdAt)}</p>
                {o.paymentId ? (
                  <p className="mt-1 text-xs text-ink-soft">
                    Оплата: {PAY_LABEL[o.paymentStatus] || o.paymentStatus}
                    {o.receiptStatus !== "none" ? ` · чек: ${o.receiptStatus}` : ""}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className="rounded-full bg-sage-light px-3 py-1 text-xs font-semibold text-sage-dark">
                  {STATUS_LABEL[o.status] || o.status}
                </span>
                <form action={updateOrderStatus} className="flex items-center gap-2">
                  <input type="hidden" name="id" value={o.id} />
                  <select name="status" defaultValue={o.status} className={`${fieldClass} py-1.5`}>
                    {Object.entries(STATUS_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                  <button className="rounded-full bg-sage px-3 py-1.5 text-xs font-semibold text-white hover:bg-sage-dark">ОК</button>
                </form>
                <form action={deleteOrder}>
                  <input type="hidden" name="id" value={o.id} />
                  <button className="text-xs font-medium text-terracotta-dark hover:underline">Удалить</button>
                </form>
              </div>
            </div>
          </Card>
        ))}
        {orders.length === 0 && <Card>Заявок пока нет.</Card>}
      </div>
    </div>
  );
}
