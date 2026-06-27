import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";

type Params = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const article = await prisma.article.findUnique({ where: { slug } });
  if (!article) return { title: "Статья не найдена" };
  return {
    title: article.metaTitle || article.title,
    description: article.metaDescription || article.excerpt,
  };
}

function formatDate(d: Date) {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(d);
}

export default async function ArticlePage({ params }: Params) {
  const { slug } = await params;
  const article = await prisma.article.findUnique({ where: { slug } });
  if (!article || !article.isPublished) notFound();

  return (
    <article className="mx-auto max-w-3xl px-4 py-14 sm:px-6 md:py-20">
      <Link href="/articles" className="text-sm font-medium text-sage-dark hover:underline">
        ← Все статьи
      </Link>
      {article.category ? (
        <span className="mt-6 block text-xs font-semibold uppercase tracking-wide text-sage-dark">
          {article.category}
        </span>
      ) : null}
      <h1 className="mt-2 text-4xl text-ink">{article.title}</h1>
      <p className="mt-3 text-sm text-ink-soft">{formatDate(article.publishedAt)}</p>

      {article.cover ? (
        <div className="relative mt-8 aspect-[16/9] overflow-hidden rounded-2xl">
          <Image src={article.cover} alt={article.title} fill sizes="800px" className="object-cover" />
        </div>
      ) : null}

      <div
        className="prose-cms mt-8 text-ink-soft"
        dangerouslySetInnerHTML={{ __html: article.content }}
      />
    </article>
  );
}
