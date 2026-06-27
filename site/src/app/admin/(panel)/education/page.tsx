import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { saveEducation, deleteEducation } from "../../_actions/cms";
import { PageHeader, Card, Field, TextArea, SaveButton } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Образование" };

export default async function EducationAdmin() {
  const items = await prisma.education.findMany({ orderBy: { order: "asc" } });

  return (
    <div>
      <PageHeader title="Образование и квалификация" description="Записи отображаются на странице «Обо мне»." />

      <Card className="mb-6">
        <h2 className="mb-4 text-lg font-semibold text-ink">Добавить запись</h2>
        <form action={saveEducation} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Название / специализация" name="title" required />
            <Field label="Учебное заведение" name="institution" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Год" name="year" />
            <Field label="Порядок" name="order" type="number" defaultValue={items.length} />
          </div>
          <TextArea label="Описание" name="description" rows={2} />
          <SaveButton>Добавить</SaveButton>
        </form>
      </Card>

      <div className="space-y-4">
        {items.map((e) => (
          <Card key={e.id}>
            <form action={saveEducation} className="space-y-4">
              <input type="hidden" name="id" value={e.id} />
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Название / специализация" name="title" defaultValue={e.title} required />
                <Field label="Учебное заведение" name="institution" defaultValue={e.institution} />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Год" name="year" defaultValue={e.year} />
                <Field label="Порядок" name="order" type="number" defaultValue={e.order} />
              </div>
              <TextArea label="Описание" name="description" defaultValue={e.description} rows={2} />
              <div className="flex gap-3">
                <SaveButton />
              </div>
            </form>
            <form action={deleteEducation} className="mt-3 border-t border-cream-deep pt-3">
              <input type="hidden" name="id" value={e.id} />
              <button className="text-sm font-medium text-terracotta-dark hover:underline">Удалить запись</button>
            </form>
          </Card>
        ))}
      </div>
    </div>
  );
}
