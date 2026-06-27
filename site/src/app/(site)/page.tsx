import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { getSettings, getBlocks } from "@/lib/content";
import { getSocialLinks, telHref } from "@/lib/socials";
import PortraitFrame from "@/components/site/PortraitFrame";
import ServiceCard from "@/components/site/ServiceCard";
import ReviewCard from "@/components/site/ReviewCard";
import DiplomaGallery from "@/components/site/DiplomaGallery";
import SocialBar from "@/components/site/SocialBar";
import {
  PhoneIcon,
  MapPinIcon,
  ClockIcon,
  CheckIcon,
  ArrowRightIcon,
  HeartIcon,
} from "@/components/icons";

export const dynamic = "force-dynamic";

const HOME_DEFAULTS = {
  hero_eyebrow: { value: "Клинический и семейный психолог · Ростов-на-Дону", label: "Хедлайн: надпись над заголовком" },
  hero_title: { value: "Помогаю вернуть опору, спокойствие и тёплые отношения", label: "Хедлайн: заголовок" },
  hero_subtitle: {
    value:
      "Бережная работа с тревогой, страхами, неуверенностью в себе и кризисами в отношениях. Индивидуально, в паре и в группе — очно в Ростове-на-Дону и онлайн.",
    label: "Хедлайн: подзаголовок",
  },
  intro_title: { value: "Если вы здесь — значит, готовы к переменам", label: "Блок «О подходе»: заголовок" },
  intro_text: {
    value:
      "Любой симптом или сложность в отношениях — это «звоночек» психики. Вместе мы бережно исследуем его причины и найдём путь к спокойствию и зрелой опоре внутри себя. Я работаю экологично, в комфортном для вас темпе и гарантирую полную конфиденциальность.",
    label: "Блок «О подходе»: текст",
  },
  services_title: { value: "Услуги и цены", label: "Услуги: заголовок" },
  services_subtitle: { value: "Выберите формат, который подходит именно вам", label: "Услуги: подзаголовок" },
  methods_title: { value: "Методы, в которых я работаю", label: "Методы: заголовок" },
  diplomas_title: { value: "Образование, дипломы и сертификаты", label: "Дипломы: заголовок" },
  diplomas_subtitle: {
    value: "Нажмите на изображение, чтобы рассмотреть подробнее",
    label: "Дипломы: подзаголовок",
  },
  steps_title: { value: "Как проходит работа", label: "Этапы: заголовок" },
  reviews_title: { value: "Отзывы клиентов", label: "Отзывы: заголовок" },
  cta_title: { value: "Сделайте первый шаг к себе", label: "Призыв: заголовок" },
  cta_text: {
    value: "Запишитесь на консультацию в удобное время — очно или онлайн.",
    label: "Призыв: текст",
  },
};

const METHODS = [
  { title: "Клиническая психология", text: "Профессиональная диагностика и работа с тревожными, депрессивными и невротическими состояниями." },
  { title: "Системная семейная терапия", text: "Помощь парам и семьям: восстановление контакта, доверия и тепла в отношениях." },
  { title: "ACT — терапия принятия", text: "Развитие психологической гибкости и умения жить в согласии со своими ценностями." },
  { title: "Эмоционально-фокусированный подход", text: "Бережная работа с эмоциями и привязанностью в паре и индивидуально." },
];

const STEPS = [
  { n: "01", title: "Знакомство и запрос", text: "На первой встрече знакомимся, проясняем ваш запрос и намечаем план работы." },
  { n: "02", title: "Бережное исследование", text: "Вместе исследуем причины состояния в безопасной и поддерживающей атмосфере." },
  { n: "03", title: "Новые опоры", text: "Осваиваем инструменты, которые помогают справляться и опираться на себя." },
  { n: "04", title: "Устойчивый результат", text: "Закрепляем изменения, чтобы они оставались с вами в жизни." },
];

export default async function HomePage() {
  const [settings, blocks, services, diplomas, reviews] = await Promise.all([
    getSettings(),
    getBlocks("home", HOME_DEFAULTS),
    prisma.service.findMany({ where: { isActive: true }, orderBy: { order: "asc" } }),
    prisma.diploma.findMany({ where: { isPublished: true }, orderBy: { order: "asc" } }),
    prisma.review.findMany({ where: { isPublished: true }, orderBy: { order: "asc" }, take: 6 }),
  ]);
  const socials = getSocialLinks(settings);

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden bg-cream">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-sage-light blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-24 h-96 w-96 rounded-full bg-cream-deep blur-3xl" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 md:grid-cols-2 md:py-24">
          <div className="animate-fade-up">
            <span className="inline-flex items-center gap-2 rounded-full bg-sage-light px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-sage-dark">
              {blocks.hero_eyebrow}
            </span>
            <h1 className="mt-5 text-4xl text-ink sm:text-5xl">{blocks.hero_title}</h1>
            <p className="mt-5 max-w-lg text-base leading-relaxed text-ink-soft sm:text-lg">
              {blocks.hero_subtitle}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/booking"
                className="inline-flex items-center gap-2 rounded-full bg-sage px-7 py-3 text-sm font-semibold text-white transition hover:bg-sage-dark"
              >
                Записаться на консультацию
                <ArrowRightIcon className="h-4 w-4" />
              </Link>
              <a
                href={telHref(settings.phone)}
                className="inline-flex items-center gap-2 rounded-full border border-sage px-7 py-3 text-sm font-semibold text-sage-dark transition hover:bg-sage-light"
              >
                <PhoneIcon className="h-4 w-4" />
                {settings.phone}
              </a>
            </div>
            <SocialBar links={socials} className="mt-8" />
          </div>

          <div className="relative mx-auto w-full max-w-sm">
            <PortraitFrame src={settings.heroPhoto} alt={settings.ownerName} className="aspect-[4/5] shadow-xl" />
            <div className="absolute -bottom-6 -left-6 hidden rounded-2xl bg-white p-4 shadow-lg sm:block">
              <p className="font-[family-name:var(--font-display)] text-lg font-semibold text-ink">
                {settings.ownerName}
              </p>
              <p className="text-xs text-ink-soft">{settings.profession}</p>
            </div>
          </div>
        </div>

        {/* facts strip */}
        <div className="relative border-t border-cream-deep bg-white/60">
          <div className="mx-auto grid max-w-6xl gap-4 px-4 py-6 sm:grid-cols-3 sm:px-6">
            <div className="flex items-center gap-3">
              <MapPinIcon className="h-5 w-5 text-sage" />
              <span className="text-sm text-ink-soft">{settings.address}</span>
            </div>
            <div className="flex items-center gap-3">
              <ClockIcon className="h-5 w-5 text-sage" />
              <span className="text-sm text-ink-soft">{settings.workingHours}</span>
            </div>
            <div className="flex items-center gap-3">
              <HeartIcon className="h-5 w-5 text-sage" />
              <span className="text-sm text-ink-soft">Конфиденциально и без осуждения</span>
            </div>
          </div>
        </div>
      </section>

      {/* Intro */}
      <section className="mx-auto max-w-4xl px-4 py-16 text-center sm:px-6 md:py-24">
        <h2 className="text-3xl text-ink sm:text-4xl">{blocks.intro_title}</h2>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-ink-soft">
          {blocks.intro_text}
        </p>
      </section>

      {/* Services */}
      <section id="services" className="bg-cream-deep/40 py-16 md:py-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="text-center">
            <h2 className="text-3xl text-ink sm:text-4xl">{blocks.services_title}</h2>
            <p className="mt-3 text-ink-soft">{blocks.services_subtitle}</p>
          </div>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {services.map((s) => (
              <ServiceCard key={s.id} service={s} />
            ))}
          </div>
          <div className="mt-10 text-center">
            <Link href="/services" className="inline-flex items-center gap-1 font-semibold text-sage-dark hover:underline">
              Подробнее об услугах <ArrowRightIcon className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Methods */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24">
        <h2 className="text-center text-3xl text-ink sm:text-4xl">{blocks.methods_title}</h2>
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {METHODS.map((m) => (
            <div key={m.title} className="rounded-2xl border border-cream-deep bg-white p-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-sage text-white">
                <CheckIcon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 text-lg text-ink">{m.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">{m.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Diplomas */}
      <section className="bg-cream-deep/40 py-16 md:py-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="text-center">
            <h2 className="text-3xl text-ink sm:text-4xl">{blocks.diplomas_title}</h2>
            <p className="mt-3 text-ink-soft">{blocks.diplomas_subtitle}</p>
          </div>
          <div className="mt-12">
            <DiplomaGallery items={diplomas} />
          </div>
        </div>
      </section>

      {/* Steps */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24">
        <h2 className="text-center text-3xl text-ink sm:text-4xl">{blocks.steps_title}</h2>
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s) => (
            <div key={s.n} className="relative rounded-2xl bg-white p-6 shadow-sm">
              <span className="font-[family-name:var(--font-display)] text-4xl font-semibold text-sage-light">
                {s.n}
              </span>
              <h3 className="mt-2 text-lg text-ink">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Reviews */}
      {reviews.length > 0 && (
        <section className="bg-cream-deep/40 py-16 md:py-24">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="text-center text-3xl text-ink sm:text-4xl">{blocks.reviews_title}</h2>
            <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {reviews.map((r) => (
                <ReviewCard key={r.id} review={r} />
              ))}
            </div>
            <div className="mt-10 text-center">
              <Link href="/reviews" className="inline-flex items-center gap-1 font-semibold text-sage-dark hover:underline">
                Все отзывы <ArrowRightIcon className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="bg-sage">
        <div className="mx-auto max-w-4xl px-4 py-16 text-center sm:px-6 md:py-20">
          <h2 className="text-3xl text-white sm:text-4xl">{blocks.cta_title}</h2>
          <p className="mx-auto mt-4 max-w-xl text-white/85">{blocks.cta_text}</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href="/booking"
              className="rounded-full bg-white px-7 py-3 text-sm font-semibold text-sage-dark transition hover:bg-cream"
            >
              Записаться онлайн
            </Link>
            <a
              href={telHref(settings.phone)}
              className="rounded-full border border-white/60 px-7 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              Позвонить: {settings.phone}
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
