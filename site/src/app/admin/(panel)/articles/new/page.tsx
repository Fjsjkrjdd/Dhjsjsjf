import type { Metadata } from "next";
import { PageHeader } from "@/components/admin/ui";
import ArticleForm from "../ArticleForm";

export const metadata: Metadata = { title: "Новая статья" };

export default function NewArticlePage() {
  return (
    <div>
      <PageHeader title="Новая статья" />
      <ArticleForm />
    </div>
  );
}
