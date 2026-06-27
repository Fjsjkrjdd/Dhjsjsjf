import type { Metadata } from "next";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { deleteArticle } from "../../_actions/cms";
import { PageHeader, Card, LinkButton } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Статьи" };

export default async function ArticlesAdmin() {
  const articles = await prisma.article.findMany({ orderBy: { publishedAt: "desc" } });

  return (
    <div>
      <PageHeader
        title="Статьи"
        description="Блог и полезные материалы."
        action={<LinkButton href="/admin/articles/new">+ Новая статья</LinkButton>}
      />
      <div className="space-y-3">
        {articles.map((a) => (
          <Card key={a.id} className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink">{a.title}</span>
                {!a.isPublished && <span className="rounded-full bg-cream-deep px-2 py-0.5 text-xs text-ink-soft">черновик</span>}
              </div>
              {a.category ? <p className="mt-0.5 text-sm text-ink-soft">{a.category}</p> : null}
            </div>
            <div className="flex items-center gap-2">
              <Link href={`/admin/articles/${a.id}`} className="rounded-full border border-cream-deep px-4 py-2 text-sm font-medium text-ink hover:bg-cream-deep/60">
                Изменить
              </Link>
              <form action={deleteArticle}>
                <input type="hidden" name="id" value={a.id} />
                <button className="rounded-full px-3 py-2 text-sm font-medium text-terracotta-dark hover:bg-cream-deep/60">Удалить</button>
              </form>
            </div>
          </Card>
        ))}
        {articles.length === 0 && <Card>Статьи ещё не созданы.</Card>}
      </div>
    </div>
  );
}
