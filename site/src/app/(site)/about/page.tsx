import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { getSettings, getBlocks } from "@/lib/content";
import PortraitFrame from "@/components/site/PortraitFrame";
import DiplomaGallery from "@/components/site/DiplomaGallery";
import { CheckIcon } from "@/components/icons";

export const metadata: Metadata = { title: "Обо мне" };
export const dynamic = "force-dynamic";

const DEFAULTS = {
  title: { value: "Обо мне", label: "Заголовок" },
  lead: {
    value:
      "Я — клинический и семейный психолог. Помогаю людям справляться с тревогой, страхами и кризисами в отношениях, бережно и без осуждения сопровождая их на пути к себе.",
    label: "Вводный абзац",
  },
  body: {
    value:
      "В своей работе я опираюсь на методы с доказанной эффективностью: клиническую психологию, системную семейную терапию, ACT (терапию принятия и ответственности) и эмоционально-фокусированный подход. Веду индивидуальные консультации, работаю с парами и семьями, провожу женскую арт-терапевтическую группу и терапевтическую игру ACT.\n\nЯ верю, что у каждого человека есть внутренние ресурсы для изменений — моя задача помочь их обнаружить и опереться на них. Гарантирую полную конфиденциальность.",
    label: "Основной текст (абзацы через пустую строку)",
  },
  edu_title: { value: "Образование и квалификация", label: "Заголовок блока образования" },
  diplomas_title: { value: "Дипломы и сертификаты", label: "Заголовок галереи дипломов" },
  diplomas_hint: { value: "Нажмите на изображение, чтобы увеличить", label: "Подсказка к галерее" },
};

export default async function AboutPage() {
  const [settings, blocks, education, diplomas] = await Promise.all([
    getSettings(),
    getBlocks("about", DEFAULTS),
    prisma.education.findMany({ orderBy: { order: "asc" } }),
    prisma.diploma.findMany({ where: { isPublished: true }, orderBy: { order: "asc" } }),
  ]);

  const paragraphs = blocks.body.split(/\n\s*\n/).filter(Boolean);

  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6 md:py-20">
      <div className="grid gap-10 md:grid-cols-[320px_1fr] md:items-start">
        <div className="mx-auto w-full max-w-xs md:sticky md:top-24">
          <PortraitFrame src={settings.aboutPhoto || settings.heroPhoto} alt={settings.ownerName} className="aspect-[4/5] shadow-lg" />
          <div className="mt-4 rounded-2xl bg-cream-deep/50 p-4 text-center">
            <p className="font-[family-name:var(--font-display)] text-xl font-semibold text-ink">{settings.ownerName}</p>
            <p className="text-sm text-ink-soft">{settings.profession}</p>
          </div>
        </div>

        <div>
          <h1 className="text-4xl text-ink sm:text-5xl">{blocks.title}</h1>
          <p className="mt-5 text-lg leading-relaxed text-ink-soft">{blocks.lead}</p>
          <div className="prose-cms mt-5 text-ink-soft">
            {paragraphs.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        </div>
      </div>

      {/* Education */}
      <section className="mt-16">
        <h2 className="text-3xl text-ink">{blocks.edu_title}</h2>
        <ol className="mt-8 space-y-5 border-l-2 border-sage-light pl-6">
          {education.map((e) => (
            <li key={e.id} className="relative">
              <span className="absolute -left-[31px] top-1 flex h-5 w-5 items-center justify-center rounded-full bg-sage text-white">
                <CheckIcon className="h-3 w-3" />
              </span>
              <h3 className="text-lg text-ink">{e.title}</h3>
              <p className="text-sm font-medium text-sage-dark">
                {[e.institution, e.year].filter(Boolean).join(" · ")}
              </p>
              {e.description ? <p className="mt-1 text-sm text-ink-soft">{e.description}</p> : null}
            </li>
          ))}
        </ol>
      </section>

      {/* Diplomas */}
      <section className="mt-16">
        <h2 className="text-3xl text-ink">{blocks.diplomas_title}</h2>
        <p className="mt-2 text-ink-soft">{blocks.diplomas_hint}</p>
        <div className="mt-8">
          <DiplomaGallery items={diplomas} />
        </div>
      </section>
    </div>
  );
}
