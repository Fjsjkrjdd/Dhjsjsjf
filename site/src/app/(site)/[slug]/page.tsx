import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";

type Params = { params: Promise<{ slug: string }> };

const RESERVED = new Set([
  "services",
  "about",
  "reviews",
  "articles",
  "contacts",
  "booking",
  "admin",
  "api",
]);

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const page = await prisma.page.findUnique({ where: { slug } });
  if (!page) return { title: "Страница не найдена" };
  return { title: page.metaTitle || page.title, description: page.metaDescription };
}

export default async function CustomPage({ params }: Params) {
  const { slug } = await params;
  if (RESERVED.has(slug)) notFound();

  const page = await prisma.page.findUnique({ where: { slug } });
  if (!page || !page.isPublished) notFound();

  return (
    <article className="mx-auto max-w-3xl px-4 py-14 sm:px-6 md:py-20">
      <h1 className="text-4xl text-ink">{page.title}</h1>
      <div className="prose-cms mt-8 text-ink-soft" dangerouslySetInnerHTML={{ __html: page.content }} />
    </article>
  );
}
