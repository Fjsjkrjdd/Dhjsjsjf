import type { Metadata } from "next";
import { PageHeader } from "@/components/admin/ui";
import PageForm from "../PageForm";

export const metadata: Metadata = { title: "Новая страница" };

export default function NewPagePage() {
  return (
    <div>
      <PageHeader title="Новая страница" />
      <PageForm />
    </div>
  );
}
