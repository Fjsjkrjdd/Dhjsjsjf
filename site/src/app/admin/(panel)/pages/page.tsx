import type { Metadata } from "next";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { deletePage } from "../../_actions/cms";
import { PageHeader, Card, LinkButton } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Страницы" };

export default async function PagesAdmin() {
  const pages = await prisma.page.findMany({ orderBy: { order: "asc" } });

  return (
    <div>
      <PageHeader
        title="Страницы"
        description="Отдельные страницы сайта (например, политика конфиденциальности)."
        action={<LinkButton href="/admin/pages/new">+ Новая страница</LinkButton>}
      />
      <div className="space-y-3">
        {pages.map((p) => (
          <Card key={p.id} className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <span className="font-semibold text-ink">{p.title}</span>
              <p className="mt-0.5 text-sm text-ink-soft">/{p.slug}{p.isPublished ? "" : " · черновик"}</p>
            </div>
            <div className="flex items-center gap-2">
              <Link href={`/admin/pages/${p.id}`} className="rounded-full border border-cream-deep px-4 py-2 text-sm font-medium text-ink hover:bg-cream-deep/60">
                Изменить
              </Link>
              <form action={deletePage}>
                <input type="hidden" name="id" value={p.id} />
                <button className="rounded-full px-3 py-2 text-sm font-medium text-terracotta-dark hover:bg-cream-deep/60">Удалить</button>
              </form>
            </div>
          </Card>
        ))}
        {pages.length === 0 && <Card>Страницы ещё не созданы.</Card>}
      </div>
    </div>
  );
}
