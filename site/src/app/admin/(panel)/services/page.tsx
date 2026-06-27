import type { Metadata } from "next";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { formatPrice } from "@/lib/content";
import { deleteService } from "../../_actions/cms";
import { PageHeader, Card, LinkButton } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Услуги" };

export default async function ServicesAdmin() {
  const services = await prisma.service.findMany({ orderBy: { order: "asc" } });

  return (
    <div>
      <PageHeader
        title="Услуги и цены"
        description="Управляйте списком услуг, ценами и описаниями."
        action={<LinkButton href="/admin/services/new">+ Добавить услугу</LinkButton>}
      />

      <div className="space-y-3">
        {services.map((s) => (
          <Card key={s.id} className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink">{s.title}</span>
                {!s.isActive && <span className="rounded-full bg-cream-deep px-2 py-0.5 text-xs text-ink-soft">скрыта</span>}
              </div>
              <p className="mt-0.5 text-sm text-ink-soft">
                {formatPrice(s.price)} ₽{s.duration ? ` · ${s.duration}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link href={`/admin/services/${s.id}`} className="rounded-full border border-cream-deep px-4 py-2 text-sm font-medium text-ink hover:bg-cream-deep/60">
                Изменить
              </Link>
              <form action={deleteService}>
                <input type="hidden" name="id" value={s.id} />
                <button className="rounded-full px-3 py-2 text-sm font-medium text-terracotta-dark hover:bg-cream-deep/60">Удалить</button>
              </form>
            </div>
          </Card>
        ))}
        {services.length === 0 && <Card>Услуги ещё не добавлены.</Card>}
      </div>
    </div>
  );
}
