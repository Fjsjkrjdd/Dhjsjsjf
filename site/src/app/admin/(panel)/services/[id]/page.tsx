import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { PageHeader } from "@/components/admin/ui";
import ServiceForm from "../ServiceForm";

export const metadata: Metadata = { title: "Редактирование услуги" };

export default async function EditServicePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const service = await prisma.service.findUnique({ where: { id } });
  if (!service) notFound();

  return (
    <div>
      <PageHeader title="Редактирование услуги" />
      <ServiceForm service={service} />
    </div>
  );
}
