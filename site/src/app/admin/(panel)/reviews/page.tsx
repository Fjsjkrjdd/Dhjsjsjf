import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { saveReview, deleteReview } from "../../_actions/cms";
import { PageHeader, Card, Field, TextArea, Checkbox, SaveButton, fieldClass } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Отзывы" };

function RatingSelect({ value }: { value?: number }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">Оценка</span>
      <select name="rating" defaultValue={value ?? 5} className={fieldClass}>
        {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n} ★</option>)}
      </select>
    </label>
  );
}

export default async function ReviewsAdmin() {
  const reviews = await prisma.review.findMany({ orderBy: { order: "asc" } });

  return (
    <div>
      <PageHeader title="Отзывы" description="Добавляйте отзывы клиентов (с их согласия)." />

      <Card className="mb-6">
        <h2 className="mb-4 text-lg font-semibold text-ink">Добавить отзыв</h2>
        <form action={saveReview} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Автор" name="author" required />
            <Field label="Источник" name="source" placeholder="Яндекс Карты" />
            <RatingSelect />
          </div>
          <TextArea label="Текст отзыва" name="text" rows={3} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Дата (текст)" name="date" placeholder="Март 2025" />
            <Field label="Порядок" name="order" type="number" defaultValue={reviews.length} />
          </div>
          <Checkbox label="Опубликован" name="isPublished" defaultChecked />
          <SaveButton>Добавить</SaveButton>
        </form>
      </Card>

      <div className="space-y-4">
        {reviews.map((r) => (
          <Card key={r.id}>
            <form action={saveReview} className="space-y-4">
              <input type="hidden" name="id" value={r.id} />
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Автор" name="author" defaultValue={r.author} required />
                <Field label="Источник" name="source" defaultValue={r.source} />
                <RatingSelect value={r.rating} />
              </div>
              <TextArea label="Текст отзыва" name="text" defaultValue={r.text} rows={3} />
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Дата (текст)" name="date" defaultValue={r.date} />
                <Field label="Порядок" name="order" type="number" defaultValue={r.order} />
              </div>
              <Checkbox label="Опубликован" name="isPublished" defaultChecked={r.isPublished} />
              <SaveButton />
            </form>
            <form action={deleteReview} className="mt-3 border-t border-cream-deep pt-3">
              <input type="hidden" name="id" value={r.id} />
              <button className="text-sm font-medium text-terracotta-dark hover:underline">Удалить отзыв</button>
            </form>
          </Card>
        ))}
      </div>
    </div>
  );
}
