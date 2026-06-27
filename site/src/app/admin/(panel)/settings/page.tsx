import type { Metadata } from "next";
import { getSettings } from "@/lib/content";
import { saveSettings } from "../../_actions/cms";
import { PageHeader, Card, Field, TextArea, Checkbox, SaveButton, Toast } from "@/components/admin/ui";
import ImagePicker from "@/components/admin/ImagePicker";

export const metadata: Metadata = { title: "Настройки сайта" };

type SP = Promise<{ saved?: string }>;

export default async function SettingsPage({ searchParams }: { searchParams: SP }) {
  const { saved } = await searchParams;
  const s = await getSettings();

  return (
    <form action={saveSettings}>
      <PageHeader title="Настройки сайта" description="Контакты, соцсети, фото, SEO и онлайн-касса." action={<SaveButton />} />
      <Toast show={!!saved}>Настройки сохранены.</Toast>

      <div className="space-y-6">
        <Card>
          <h2 className="mb-4 text-lg font-semibold text-ink">Основное</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Название сайта" name="siteName" defaultValue={s.siteName} />
            <Field label="Текст логотипа" name="logoText" defaultValue={s.logoText} />
            <Field label="Имя специалиста" name="ownerName" defaultValue={s.ownerName} />
            <Field label="Профессия / должность" name="profession" defaultValue={s.profession} />
          </div>
          <div className="mt-4">
            <TextArea label="Слоган" name="tagline" defaultValue={s.tagline} rows={2} />
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-lg font-semibold text-ink">Фотографии</h2>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <input type="hidden" name="heroPhoto" defaultValue={s.heroPhoto} />
              <ImagePicker name="heroPhotoFile" label="Главное фото (обложка)" current={s.heroPhoto} hint="Используется в шапке и на странице «Обо мне»." />
            </div>
            <div>
              <input type="hidden" name="aboutPhoto" defaultValue={s.aboutPhoto} />
              <ImagePicker name="aboutPhotoFile" label="Фото для страницы «Обо мне»" current={s.aboutPhoto} />
            </div>
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-lg font-semibold text-ink">Контакты</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Телефон" name="phone" defaultValue={s.phone} />
            <Field label="E-mail" name="email" defaultValue={s.email} />
            <Field label="Город" name="city" defaultValue={s.city} />
            <Field label="Время работы" name="workingHours" defaultValue={s.workingHours} />
          </div>
          <div className="mt-4">
            <Field label="Адрес" name="address" defaultValue={s.address} />
          </div>
          <div className="mt-4">
            <TextArea
              label="Карта (HTML-код виджета Яндекс.Карт)"
              name="mapEmbed"
              defaultValue={s.mapEmbed}
              rows={3}
              hint="Вставьте код <iframe ...> из конструктора Яндекс.Карт. Если пусто — покажем ссылку на карты."
            />
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-lg font-semibold text-ink">Социальные сети</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="ВКонтакте (ссылка)" name="vk" defaultValue={s.vk} placeholder="https://vk.com/..." />
            <Field label="Telegram (@ник или ссылка)" name="telegram" defaultValue={s.telegram} />
            <Field label="WhatsApp (номер или ссылка)" name="whatsapp" defaultValue={s.whatsapp} />
            <Field label="Instagram (ссылка)" name="instagram" defaultValue={s.instagram} />
            <Field label="YouTube (ссылка)" name="youtube" defaultValue={s.youtube} />
            <Field label="Яндекс Карты (ссылка)" name="yandexMaps" defaultValue={s.yandexMaps} />
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-lg font-semibold text-ink">SEO</h2>
          <div className="space-y-4">
            <Field label="Заголовок (title)" name="metaTitle" defaultValue={s.metaTitle} />
            <TextArea label="Описание (description)" name="metaDescription" defaultValue={s.metaDescription} rows={2} />
          </div>
        </Card>

        <Card>
          <h2 id="payments" className="mb-1 text-lg font-semibold text-ink">Онлайн-касса (ЮKassa)</h2>
          <p className="mb-4 text-sm text-ink-soft">
            Подключите ЮKassa, чтобы принимать оплату на сайте. Данные магазина (shopId и секретный ключ)
            берутся в личном кабинете ЮKassa. Секретный ключ хранится на сервере и не отображается.
          </p>
          <div className="space-y-4">
            <Checkbox label="Принимать онлайн-оплату" name="paymentsEnabled" defaultChecked={s.paymentsEnabled} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="shopId (идентификатор магазина)" name="yooKassaShopId" defaultValue={s.yooKassaShopId} />
              <Field
                label="Секретный ключ"
                name="yooKassaSecretKey"
                type="password"
                placeholder={s.yooKassaSecretKey ? "•••••• (сохранён, оставьте пустым, чтобы не менять)" : "test_... или live_..."}
              />
            </div>

            <div className="rounded-xl bg-cream-deep/40 p-4">
              <Checkbox label="Формировать кассовые чеки (54-ФЗ)" name="fiscalEnabled" defaultChecked={s.fiscalEnabled} />
              <p className="mt-1 text-xs text-ink-soft">
                Включите, если ваша касса в ЮKassa настроена на фискализацию. Тогда при оплате клиенту будет приходить чек.
              </p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-ink">Система налогообложения</span>
                  <select name="taxSystemCode" defaultValue={s.taxSystemCode} className="w-full rounded-lg border border-cream-deep bg-white px-3.5 py-2.5 text-sm">
                    <option value={1}>ОСН</option>
                    <option value={2}>УСН доход</option>
                    <option value={3}>УСН доход-расход</option>
                    <option value={4}>ЕНВД</option>
                    <option value={5}>ЕСХН</option>
                    <option value={6}>Патент</option>
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-ink">Ставка НДС</span>
                  <select name="vatCode" defaultValue={s.vatCode} className="w-full rounded-lg border border-cream-deep bg-white px-3.5 py-2.5 text-sm">
                    <option value={1}>Без НДС</option>
                    <option value={2}>0%</option>
                    <option value={3}>10%</option>
                    <option value={4}>20%</option>
                    <option value={5}>10/110</option>
                    <option value={6}>20/120</option>
                  </select>
                </label>
              </div>
            </div>
          </div>
          <input type="hidden" name="paymentProvider" value="yookassa" />
        </Card>

        <div className="flex justify-end">
          <SaveButton />
        </div>
      </div>
    </form>
  );
}
