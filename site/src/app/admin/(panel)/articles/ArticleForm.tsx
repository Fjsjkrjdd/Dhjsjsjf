import type { Article } from "@prisma/client";
import { saveArticle } from "../../_actions/cms";
import { Card, Field, TextArea, Checkbox, SaveButton, LinkButton } from "@/components/admin/ui";
import ImagePicker from "@/components/admin/ImagePicker";

export default function ArticleForm({ article }: { article?: Article | null }) {
  return (
    <form action={saveArticle}>
      {article ? <input type="hidden" name="id" value={article.id} /> : null}
      <Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Заголовок" name="title" defaultValue={article?.title} required />
          <Field label="URL (slug)" name="slug" defaultValue={article?.slug} hint="Оставьте пустым для автогенерации" />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Категория" name="category" defaultValue={article?.category} placeholder="Тревога, Отношения…" />
          <div>
            <input type="hidden" name="cover" defaultValue={article?.cover} />
            <ImagePicker name="coverFile" label="Обложка" current={article?.cover} />
          </div>
        </div>
        <div className="mt-4">
          <TextArea label="Краткое описание (анонс)" name="excerpt" defaultValue={article?.excerpt} rows={2} />
        </div>
        <div className="mt-4">
          <TextArea
            label="Текст статьи (HTML)"
            name="content"
            defaultValue={article?.content}
            rows={12}
            hint="Поддерживается HTML: <p>, <h2>, <ul>, <a> и т.д."
          />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="SEO заголовок" name="metaTitle" defaultValue={article?.metaTitle} />
          <Field label="SEO описание" name="metaDescription" defaultValue={article?.metaDescription} />
        </div>
        <div className="mt-4">
          <Checkbox label="Опубликована" name="isPublished" defaultChecked={article ? article.isPublished : true} />
        </div>
        <div className="mt-6 flex gap-3">
          <SaveButton />
          <LinkButton href="/admin/articles" variant="ghost">Отмена</LinkButton>
        </div>
      </Card>
    </form>
  );
}
