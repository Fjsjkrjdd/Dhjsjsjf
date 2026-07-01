import Image from "next/image";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { getSettings, getBlocks } from "@/lib/content";
import { getSocialLinks, telHref } from "@/lib/socials";
import BookingForm from "@/components/site/BookingForm";
import PortraitFrame from "@/components/site/PortraitFrame";
import ServiceCard from "@/components/site/ServiceCard";
import SocialBar from "@/components/site/SocialBar";
import {
  ArrowRightIcon,
  CheckIcon,
  HeartIcon,
  PhoneIcon,
} from "@/components/icons";
import { BLOCK_DEFAULTS } from "@/lib/blockDefaults";

export const dynamic = "force-dynamic";

const SUPPORT_REASONS = [
  {
    n: "01",
    title: "Когда тревога и напряжение не отпускают",
    text: "Если мысли крутятся по кругу, тело всё время в напряжении, а отдых не приносит облегчения — это повод бережно обратиться за поддержкой.",
  },
  {
    n: "02",
    title: "Когда в отношениях стало холодно или больно",
    text: "Конфликты, дистанция, измена или потеря доверия требуют спокойного пространства, где можно разобраться в чувствах и дальнейших шагах.",
  },
  {
    n: "03",
    title: "Когда нет сил и энергии",
    text: "Эмоциональное истощение, раздражительность и ощущение, что вы больше не справляетесь, можно исследовать без самокритики и давления.",
  },
  {
    n: "04",
    title: "Когда повторяются одни и те же сценарии",
    text: "Повторяющиеся ситуации в любви, семье или работе часто связаны с внутренними установками. Их можно заметить и постепенно изменить.",
  },
];

const APPROACH = [
  "Клиническая психология и диагностика состояния",
  "Системная семейная терапия для пар и семей",
  "ACT — терапия принятия и ответственности",
  "Эмоционально-фокусированный и арт-терапевтический подход",
];

const FIRST_MEETING = [
  {
    title: "Обсуждаем ваш запрос",
    text: "Вы спокойно рассказываете, что сейчас беспокоит, в своём темпе и в том объёме, в котором готовы.",
  },
  {
    title: "Определяем основную проблему",
    text: "Аккуратно проясняем, что именно вызывает напряжение, чтобы увидеть ситуацию целостно и без самокритики.",
  },
  {
    title: "Намечаем возможные шаги",
    text: "Я предложу варианты дальнейшей работы, чтобы изменения были постепенными, понятными и устойчивыми.",
  },
  {
    title: "Понимаем, подходит ли формат",
    text: "Вы сможете почувствовать, комфортно ли вам со мной и таким подходом. Решение всегда остаётся за вами.",
  },
];

const STATS = [
  ["700+", "часов профильного обучения"],
  ["5+", "лет практики"],
  ["100%", "конфиденциальность"],
  ["30", "минут на первую встречу"],
];

export default async function HomePage() {
  const [settings, blocks, services, articles] = await Promise.all([
    getSettings(),
    getBlocks("home", BLOCK_DEFAULTS.home.blocks),
    prisma.service.findMany({
      where: { isActive: true },
      orderBy: { order: "asc" },
    }),
    prisma.article.findMany({
      where: { isPublished: true },
      orderBy: { publishedAt: "desc" },
      take: 3,
    }),
  ]);
  const socials = getSocialLinks(settings);
  const bookableServices = services.filter((service) => service.isBookable);

  return (
    <main className="overflow-hidden bg-[#f7f2eb] text-ink">
      <section
        id="home"
        className="relative min-h-[calc(100vh-72px)] bg-[#ece1d3]"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_16%_16%,rgba(255,255,255,.8),transparent_28%),radial-gradient(circle_at_82%_12%,rgba(213,187,159,.55),transparent_25%)]" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.02fr_.98fr] lg:py-24">
          <div className="z-10 max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[.38em] text-[#9b7b62]">
              Психолог онлайн и очно
            </p>
            <h1 className="mt-5 text-5xl leading-[.95] text-[#252321] sm:text-6xl lg:text-7xl">
              {settings.ownerName}
            </h1>
            <h2 className="mt-7 max-w-xl text-2xl font-medium leading-snug text-[#3d3934] sm:text-3xl">
              Работа с тревогой, самооценкой и кризисами в отношениях
            </h2>
            <p className="mt-7 max-w-xl whitespace-pre-line text-lg leading-relaxed text-[#6e6258]">
              {blocks.hero_subtitle}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                href="/booking"
                className="group inline-flex items-center gap-3 rounded-full bg-[#2f2d2b] px-7 py-4 text-sm font-semibold uppercase tracking-[.12em] text-white shadow-xl transition hover:bg-[#9b7b62]"
              >
                Записаться на консультацию{" "}
                <ArrowRightIcon className="h-4 w-4 transition group-hover:translate-x-1" />
              </Link>
              <a
                href={telHref(settings.phone)}
                className="inline-flex items-center gap-2 text-lg font-semibold text-[#2f2d2b]"
              >
                <PhoneIcon className="h-5 w-5" /> {settings.phone}
              </a>
            </div>
            <SocialBar links={socials} className="mt-7" />
          </div>
          <div className="relative mx-auto w-full max-w-[560px]">
            <div className="absolute -left-8 top-8 h-44 w-44 rounded-full border border-[#bfa48d]/50" />
            <div className="absolute -right-4 bottom-10 h-32 w-32 rounded-full bg-[#d8c6b3]" />
            <PortraitFrame
              src={settings.heroPhoto}
              alt={settings.ownerName}
              className="relative aspect-[4/5] rounded-t-full rounded-b-[2.5rem] shadow-2xl"
            />
          </div>
        </div>
      </section>

      <section className="bg-[#f7f2eb] py-16 md:py-24">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 sm:px-6 lg:grid-cols-[.9fr_1.1fr]">
          <div className="rounded-[2rem] bg-[#2f2d2b] p-8 text-white shadow-xl lg:p-10">
            <p className="text-xs font-semibold uppercase tracking-[.32em] text-[#d8c6b3]">
              Можно начать с малого
            </p>
            <h2 className="mt-4 text-4xl text-white">
              Иногда самый сложный шаг — написать.
            </h2>
            <p className="mt-5 text-white/75">
              Вы можете записаться на первую консультацию и спокойно разобраться
              в своём состоянии.
            </p>
            <p className="mt-6 text-2xl font-semibold">{settings.phone}</p>
            <SocialBar links={socials} className="mt-5" />
          </div>
          {bookableServices.length > 0 && (
            <BookingForm
              services={bookableServices}
              paymentsEnabled={settings.paymentsEnabled}
            />
          )}
        </div>
      </section>

      <section
        id="about"
        className="mx-auto grid max-w-7xl gap-12 px-4 py-16 sm:px-6 md:py-24 lg:grid-cols-[.85fr_1.15fr]"
      >
        <div className="relative min-h-[420px]">
          <PortraitFrame
            src={settings.heroPhoto}
            alt={settings.ownerName}
            className="absolute inset-0 aspect-auto rounded-[2.5rem]"
          />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.32em] text-[#9b7b62]">
            Давайте знакомиться
          </p>
          <h2 className="mt-4 text-4xl sm:text-5xl">
            Я — {settings.ownerName}, {settings.profession.toLowerCase()}.
          </h2>
          <p className="mt-6 text-lg leading-relaxed text-ink-soft">
            Провожу консультации для взрослых, пар и семей онлайн, а также
            работаю очно в Ростове-на-Дону.
          </p>
          <div className="mt-10 grid gap-5 sm:grid-cols-2">
            {SUPPORT_REASONS.map((item) => (
              <article
                key={item.n}
                className="rounded-[1.75rem] border border-[#e1d4c4] bg-white/70 p-6"
              >
                <span className="text-xs font-bold tracking-[.28em] text-[#9b7b62]">
                  {item.n}
                </span>
                <h3 className="mt-4 text-xl">{item.title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-ink-soft">
                  {item.text}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#2f2d2b] py-10 text-white">
        <div className="mx-auto grid max-w-7xl gap-6 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
          {STATS.map(([value, label]) => (
            <div key={label}>
              <div className="text-5xl font-semibold">{value}</div>
              <p className="mt-2 text-white/65">{label}</p>
            </div>
          ))}
        </div>
      </section>

      <section
        id="approach"
        className="mx-auto grid max-w-7xl gap-10 px-4 py-16 sm:px-6 md:py-24 lg:grid-cols-2"
      >
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.32em] text-[#9b7b62]">
            Как проходит работа с психологом
          </p>
          <h2 className="mt-4 text-4xl sm:text-5xl">Мой подход</h2>
          <p className="mt-6 text-lg leading-relaxed text-ink-soft">
            Моя задача — помочь вам выйти из замкнутого круга и вернуть ощущение
            внутренней опоры. Я работаю бережно, конфиденциально и в понятном
            темпе.
          </p>
          <ul className="mt-8 space-y-4">
            {APPROACH.map((item) => (
              <li key={item} className="flex gap-3 text-ink-soft">
                <CheckIcon className="mt-1 h-5 w-5 shrink-0 text-[#9b7b62]" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-[2.5rem] bg-[#e7dacb] p-4">
          <PortraitFrame
            src={settings.heroPhoto}
            alt={settings.ownerName}
            className="aspect-[5/4] rounded-[2rem]"
          />
        </div>
      </section>

      {services.length > 0 && (
        <section id="services" className="bg-[#ece1d3] py-16 md:py-24">
          <div className="mx-auto max-w-7xl px-4 sm:px-6">
            <p className="text-center text-xs font-semibold uppercase tracking-[.32em] text-[#9b7b62]">
              Услуги
            </p>
            <h2 className="mt-4 text-center text-4xl sm:text-5xl">
              Форматы консультаций
            </h2>
            <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {services.slice(0, 6).map((s) => (
                <ServiceCard key={s.id} service={s} />
              ))}
            </div>
          </div>
        </section>
      )}

      <section
        id="first-meeting"
        className="mx-auto max-w-7xl px-4 py-16 sm:px-6 md:py-24"
      >
        <p className="text-xs font-semibold uppercase tracking-[.32em] text-[#9b7b62]">
          Первая консультация
        </p>
        <h2 className="mt-4 text-4xl sm:text-5xl">
          Первая встреча — это 30 минут, где мы:
        </h2>
        <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {FIRST_MEETING.map((item, index) => (
            <article
              key={item.title}
              className="rounded-[2rem] bg-white p-7 shadow-sm"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#2f2d2b] text-white">
                {index + 1}
              </div>
              <h3 className="mt-6 text-xl">{item.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft">
                {item.text}
              </p>
            </article>
          ))}
        </div>
      </section>

      {articles.length > 0 && (
        <section className="bg-[#f7f2eb] py-16 md:py-24">
          <div className="mx-auto max-w-7xl px-4 sm:px-6">
            <p className="text-xs font-semibold uppercase tracking-[.32em] text-[#9b7b62]">
              Блог
            </p>
            <h2 className="mt-4 text-4xl sm:text-5xl">Спокойно о сложном</h2>
            <div className="mt-10 grid gap-6 md:grid-cols-3">
              {articles.map((article) => (
                <Link
                  key={article.id}
                  href={`/articles/${article.slug}`}
                  className="group overflow-hidden rounded-[2rem] bg-white shadow-sm"
                >
                  <div className="relative aspect-[4/3] bg-[#e7dacb]">
                    {article.cover ? (
                      <Image
                        src={article.cover}
                        alt=""
                        fill
                        className="object-cover transition duration-500 group-hover:scale-105"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center">
                        <HeartIcon className="h-10 w-10 text-[#9b7b62]" />
                      </div>
                    )}
                  </div>
                  <div className="p-6">
                    <h3 className="text-2xl group-hover:text-[#9b7b62]">
                      {article.title}
                    </h3>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <section id="contacts" className="bg-[#2f2d2b] text-white">
        <div className="mx-auto grid max-w-7xl gap-8 px-4 py-16 sm:px-6 md:py-24 lg:grid-cols-[1fr_.8fr]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[.32em] text-[#d8c6b3]">
              Связаться со мной
            </p>
            <h2 className="mt-4 text-4xl text-white sm:text-5xl">
              Вы можете написать или позвонить мне в удобном формате.
            </h2>
            <p className="mt-5 text-white/70">
              Я отвечаю лично и стараюсь делать это в течение дня.
            </p>
            <a
              href={telHref(settings.phone)}
              className="mt-8 inline-block text-3xl font-semibold text-white"
            >
              {settings.phone}
            </a>
            <SocialBar links={socials} className="mt-6" />
          </div>
          <div className="rounded-[2rem] border border-white/15 p-8 text-xl leading-relaxed text-white/75">
            Я не исправляю людей — я помогаю им бережно вернуть связь с собой.
          </div>
        </div>
      </section>
    </main>
  );
}
