import type { Page } from "@prisma/client";
import { savePage } from "../../_actions/cms";
import { Card, Field, TextArea, Checkbox, SaveButton, LinkButton } from "@/components/admin/ui";

export default function PageForm({ page }: { page?: Page | null }) {
  return (
    <form action={savePage}>
      {page ? <input type="hidden" name="id" value={page.id} /> : null}
      <Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Заголовок" name="title" defaultValue={page?.title} required />
          <Field label="URL (slug)" name="slug" defaultValue={page?.slug} hint="Например: privacy → /privacy" />
        </div>
        <div className="mt-4">
          <TextArea label="Содержимое (HTML)" name="content" defaultValue={page?.content} rows={12} hint="Поддерживается HTML." />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="SEO заголовок" name="metaTitle" defaultValue={page?.metaTitle} />
          <Field label="SEO описание" name="metaDescription" defaultValue={page?.metaDescription} />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Порядок" name="order" type="number" defaultValue={page?.order ?? 0} />
        </div>
        <div className="mt-4 flex flex-wrap gap-6">
          <Checkbox label="Опубликована" name="isPublished" defaultChecked={page ? page.isPublished : true} />
          <Checkbox label="Показывать в меню" name="showInMenu" defaultChecked={page ? page.showInMenu : false} />
        </div>
        <div className="mt-6 flex gap-3">
          <SaveButton />
          <LinkButton href="/admin/pages" variant="ghost">Отмена</LinkButton>
        </div>
      </Card>
    </form>
  );
}
