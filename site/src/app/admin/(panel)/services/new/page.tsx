import type { Metadata } from "next";
import { PageHeader } from "@/components/admin/ui";
import ServiceForm from "../ServiceForm";

export const metadata: Metadata = { title: "Новая услуга" };

export default function NewServicePage() {
  return (
    <div>
      <PageHeader title="Новая услуга" />
      <ServiceForm />
    </div>
  );
}
