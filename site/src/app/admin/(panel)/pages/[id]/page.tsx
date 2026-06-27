import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { PageHeader } from "@/components/admin/ui";
import PageForm from "../PageForm";

export const metadata: Metadata = { title: "Редактирование страницы" };

export default async function EditPagePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const page = await prisma.page.findUnique({ where: { id } });
  if (!page) notFound();
  return (
    <div>
      <PageHeader title="Редактирование страницы" />
      <PageForm page={page} />
    </div>
  );
}
