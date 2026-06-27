import type { Service } from "@prisma/client";
import { saveService } from "../../_actions/cms";
import { Card, Field, TextArea, Checkbox, SaveButton, LinkButton, fieldClass } from "@/components/admin/ui";
import ImagePicker from "@/components/admin/ImagePicker";

const ICONS = [
  { v: "user", l: "Человек (индивидуально)" },
  { v: "users", l: "Пара / семья" },
  { v: "palette", l: "Палитра (арт-терапия)" },
  { v: "sparkles", l: "Искры (игра/группа)" },
  { v: "video", l: "Видео (онлайн)" },
  { v: "heart", l: "Сердце" },
];

export default function ServiceForm({ service }: { service?: Service | null }) {
  return (
    <form action={saveService}>
      {service ? <input type="hidden" name="id" value={service.id} /> : null}
      <Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Название" name="title" defaultValue={service?.title} required />
          <Field label="URL (slug)" name="slug" defaultValue={service?.slug} hint="Оставьте пустым для автогенерации" />
        </div>
        <div className="mt-4">
          <TextArea label="Краткое описание" name="shortDescription" defaultValue={service?.shortDescription} rows={2} hint="Показывается на карточке услуги" />
        </div>
        <div className="mt-4">
          <TextArea label="Полное описание" name="description" defaultValue={service?.description} rows={5} />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Field label="Цена, ₽" name="price" type="number" defaultValue={service?.price} />
          <Field label="Старая цена, ₽" name="oldPrice" type="number" defaultValue={service?.oldPrice ?? ""} hint="Для зачёркивания" />
          <Field label="Длительность" name="duration" defaultValue={service?.duration} placeholder="60 минут" />
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-ink">Иконка</span>
            <select name="icon" defaultValue={service?.icon || "heart"} className={fieldClass}>
              {ICONS.map((i) => <option key={i.v} value={i.v}>{i.l}</option>)}
            </select>
          </label>
          <Field label="Порядок" name="order" type="number" defaultValue={service?.order ?? 0} />
        </div>
        <div className="mt-4">
          <input type="hidden" name="image" defaultValue={service?.image} />
          <ImagePicker name="imageFile" label="Изображение (необязательно)" current={service?.image} />
        </div>
        <div className="mt-4 flex flex-wrap gap-6">
          <Checkbox label="Активна (показывать на сайте)" name="isActive" defaultChecked={service ? service.isActive : true} />
          <Checkbox label="Доступна для записи / оплаты" name="isBookable" defaultChecked={service ? service.isBookable : true} />
        </div>
        <div className="mt-6 flex gap-3">
          <SaveButton />
          <LinkButton href="/admin/services" variant="ghost">Отмена</LinkButton>
        </div>
      </Card>
    </form>
  );
}
