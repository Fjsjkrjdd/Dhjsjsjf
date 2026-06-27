import Link from "next/link";
import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { getSettings } from "@/lib/content";
import { isPaymentsConfigured } from "@/lib/yookassa";
import { PageHeader, Card } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Обзор" };

export default async function DashboardPage() {
  const [settings, services, diplomas, reviews, articles, newOrders, paidOrders] = await Promise.all([
    getSettings(),
    prisma.service.count(),
    prisma.diploma.count(),
    prisma.review.count(),
    prisma.article.count(),
    prisma.order.count({ where: { status: "new" } }),
    prisma.order.count({ where: { status: "paid" } }),
  ]);

  const stats = [
    { label: "Услуги", value: services, href: "/admin/services" },
    { label: "Дипломы", value: diplomas, href: "/admin/diplomas" },
    { label: "Отзывы", value: reviews, href: "/admin/reviews" },
    { label: "Статьи", value: articles, href: "/admin/articles" },
    { label: "Новые заявки", value: newOrders, href: "/admin/orders" },
    { label: "Оплачено", value: paidOrders, href: "/admin/orders" },
  ];

  const payReady = isPaymentsConfigured(settings);

  return (
    <div>
      <PageHeader title="Добро пожаловать!" description="Здесь вы управляете всем содержимым сайта." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {stats.map((s) => (
          <Link key={s.label} href={s.href}>
            <Card className="transition hover:border-sage hover:shadow-md">
              <p className="text-sm text-ink-soft">{s.label}</p>
              <p className="mt-1 font-[family-name:var(--font-display)] text-4xl font-semibold text-ink">{s.value}</p>
            </Card>
          </Link>
        ))}
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="text-lg font-semibold text-ink">Онлайн-касса</h2>
          <p className="mt-2 text-sm text-ink-soft">
            {payReady
              ? "Онлайн-оплата настроена и активна. Клиенты могут оплачивать консультации на сайте."
              : "Онлайн-оплата ещё не настроена. Укажите данные ЮKassa в настройках, чтобы принимать платежи и формировать чеки (54-ФЗ)."}
          </p>
          <Link href="/admin/settings#payments" className="mt-3 inline-block text-sm font-semibold text-sage-dark hover:underline">
            Перейти к настройкам оплаты →
          </Link>
        </Card>
        <Card>
          <h2 className="text-lg font-semibold text-ink">Быстрые действия</h2>
          <ul className="mt-2 space-y-1.5 text-sm">
            <li><Link href="/admin/content?page=home" className="text-sage-dark hover:underline">Изменить тексты на главной</Link></li>
            <li><Link href="/admin/diplomas" className="text-sage-dark hover:underline">Загрузить дипломы и сертификаты</Link></li>
            <li><Link href="/admin/services" className="text-sage-dark hover:underline">Обновить услуги и цены</Link></li>
            <li><Link href="/admin/settings" className="text-sage-dark hover:underline">Контакты и соцсети</Link></li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
