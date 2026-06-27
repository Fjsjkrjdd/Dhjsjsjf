import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * YooKassa sends notifications here (payment.succeeded, payment.canceled, etc.).
 * Configure this URL in the YooKassa dashboard:
 *   {BASE_URL}/api/payments/webhook
 */
export async function POST(req: Request) {
  let body: { event?: string; object?: { id?: string; status?: string; paid?: boolean; metadata?: { orderId?: string } } };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400 });
  }

  const obj = body.object;
  if (!obj?.id) return NextResponse.json({ ok: true });

  const order = await prisma.order.findFirst({
    where: {
      OR: [
        { paymentId: obj.id },
        ...(obj.metadata?.orderId ? [{ id: obj.metadata.orderId }] : []),
      ],
    },
  });
  if (!order) return NextResponse.json({ ok: true });

  const succeeded = body.event === "payment.succeeded" || obj.status === "succeeded";
  const canceled = body.event === "payment.canceled" || obj.status === "canceled";

  await prisma.order.update({
    where: { id: order.id },
    data: {
      paymentId: obj.id,
      paymentStatus: obj.status ?? order.paymentStatus,
      status: succeeded ? "paid" : canceled ? "cancelled" : order.status,
      receiptStatus: succeeded && order.receiptStatus === "pending" ? "registered" : order.receiptStatus,
    },
  });

  return NextResponse.json({ ok: true });
}
