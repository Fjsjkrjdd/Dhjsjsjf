import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { prisma } from "@/lib/prisma";
import { getBlocks } from "@/lib/content";
import { BLOCK_DEFAULTS } from "@/lib/blockDefaults";

export const metadata: Metadata = { title: "Статьи" };
export const dynamic = "force-dynamic";

function formatDate(d: Date) {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(d);
}

export default async function ArticlesPage() {
  const [blocks, articles] = await Promise.all([
    getBlocks("articles", BLOCK_DEFAULTS.articles.blocks),
    prisma.article.findMany({ where: { isPublished: true }, orderBy: { publishedAt: "desc" } }),
  ]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 md:py-20">
      <h1 className="text-4xl text-ink sm:text-5xl">{blocks.title}</h1>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">{blocks.subtitle}</p>

      {articles.length === 0 ? (
        <p className="mt-12 rounded-2xl border border-dashed border-cream-deep p-8 text-center text-ink-soft">
          Статьи пока не опубликованы.
        </p>
      ) : (
        <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {articles.map((a) => (
            <Link
              key={a.id}
              href={`/articles/${a.slug}`}
              className="group flex flex-col overflow-hidden rounded-2xl border border-cream-deep bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
            >
              <div className="relative aspect-[16/10] bg-sage-light">
                {a.cover ? (
                  <Image src={a.cover} alt={a.title} fill sizes="400px" className="object-cover transition group-hover:scale-105" />
                ) : (
                  <div className="flex h-full items-center justify-center text-sage-dark/40">
                    <span className="font-[family-name:var(--font-display)] text-4xl">Статья</span>
                  </div>
                )}
              </div>
              <div className="flex flex-1 flex-col p-5">
                {a.category ? (
                  <span className="text-xs font-semibold uppercase tracking-wide text-sage-dark">{a.category}</span>
                ) : null}
                <h2 className="mt-2 text-lg text-ink">{a.title}</h2>
                <p className="mt-2 flex-1 text-sm text-ink-soft">{a.excerpt}</p>
                <span className="mt-4 text-xs text-ink-soft">{formatDate(a.publishedAt)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
