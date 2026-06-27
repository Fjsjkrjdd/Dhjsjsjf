import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { PageHeader } from "@/components/admin/ui";
import ArticleForm from "../ArticleForm";

export const metadata: Metadata = { title: "Редактирование статьи" };

export default async function EditArticlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const article = await prisma.article.findUnique({ where: { id } });
  if (!article) notFound();
  return (
    <div>
      <PageHeader title="Редактирование статьи" />
      <ArticleForm article={article} />
    </div>
  );
}
