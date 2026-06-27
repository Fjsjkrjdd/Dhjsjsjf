import type { Metadata } from "next";
import Image from "next/image";
import { prisma } from "@/lib/prisma";
import { saveDiploma, deleteDiploma } from "../../_actions/cms";
import { PageHeader, Card, Field, SaveButton, Toast } from "@/components/admin/ui";
import ImagePicker from "@/components/admin/ImagePicker";

export const metadata: Metadata = { title: "Дипломы" };

type SP = Promise<{ error?: string }>;

export default async function DiplomasAdmin({ searchParams }: { searchParams: SP }) {
  const { error } = await searchParams;
  const diplomas = await prisma.diploma.findMany({ orderBy: { order: "asc" } });

  return (
    <div>
      <PageHeader title="Дипломы и сертификаты" description="Загрузите изображения. На сайте они отображаются горизонтальной лентой с увеличением по клику." />
      {error === "image" && <Toast show><span className="text-terracotta-dark">Выберите изображение для загрузки.</span></Toast>}

      <Card className="mb-6">
        <h2 className="mb-4 text-lg font-semibold text-ink">Добавить диплом</h2>
        <form action={saveDiploma} className="space-y-4">
          <ImagePicker name="imageFile" label="Изображение диплома / сертификата" hint="JPG, PNG, WEBP" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Подпись" name="title" placeholder="Напр.: Московский институт психоанализа" />
            <Field label="Порядок" name="order" type="number" defaultValue={diplomas.length} />
          </div>
          <Field label="Описание (необязательно)" name="description" />
          <input type="hidden" name="isPublished" value="on" />
          <SaveButton>Загрузить</SaveButton>
        </form>
      </Card>

      {diplomas.length === 0 ? (
        <Card>Дипломы ещё не загружены.</Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {diplomas.map((d) => (
            <Card key={d.id} className="p-3">
              <div className="relative aspect-[3/4] overflow-hidden rounded-lg bg-cream-deep/40">
                <Image src={d.image} alt={d.title} fill sizes="200px" className="object-cover" />
              </div>
              <p className="mt-2 truncate text-sm font-medium text-ink" title={d.title}>{d.title}</p>
              <p className="text-xs text-ink-soft">Порядок: {d.order}{d.isPublished ? "" : " · скрыт"}</p>
              <form action={deleteDiploma} className="mt-2">
                <input type="hidden" name="id" value={d.id} />
                <button className="w-full rounded-lg border border-cream-deep py-1.5 text-sm font-medium text-terracotta-dark hover:bg-cream-deep/60">
                  Удалить
                </button>
              </form>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
