import Link from "next/link";
import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { getBlocks, formatPrice } from "@/lib/content";
import { ServiceIcon, ClockIcon, ArrowRightIcon } from "@/components/icons";
import { BLOCK_DEFAULTS } from "@/lib/blockDefaults";

export const metadata: Metadata = { title: "Услуги и цены" };
export const dynamic = "force-dynamic";

export default async function ServicesPage() {
  const [blocks, services] = await Promise.all([
    getBlocks("services", BLOCK_DEFAULTS.services.blocks),
    prisma.service.findMany({ where: { isActive: true }, orderBy: { order: "asc" } }),
  ]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6 md:py-20">
      <h1 className="text-4xl text-ink sm:text-5xl">{blocks.title}</h1>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">{blocks.subtitle}</p>

      <div className="mt-12 space-y-6">
        {services.map((s) => (
          <article
            key={s.id}
            className="grid gap-6 rounded-2xl border border-cream-deep bg-white p-6 shadow-sm md:grid-cols-[auto_1fr_auto] md:items-center md:p-8"
          >
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-sage-light text-sage-dark">
              <ServiceIcon name={s.icon} className="h-7 w-7" />
            </div>
            <div>
              <h2 className="text-2xl text-ink">{s.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">{s.description || s.shortDescription}</p>
              {s.duration ? (
                <span className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-sage-dark">
                  <ClockIcon className="h-4 w-4" /> {s.duration}
                </span>
              ) : null}
            </div>
            <div className="flex flex-col items-start gap-3 md:items-end">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-semibold text-ink">{formatPrice(s.price)} ₽</span>
                {s.oldPrice ? (
                  <span className="text-sm text-ink-soft line-through">{formatPrice(s.oldPrice)} ₽</span>
                ) : null}
              </div>
              {s.isBookable && (
                <Link
                  href={`/booking?service=${s.slug}`}
                  className="inline-flex items-center gap-1.5 rounded-full bg-sage px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-sage-dark"
                >
                  Записаться <ArrowRightIcon className="h-4 w-4" />
                </Link>
              )}
            </div>
          </article>
        ))}
      </div>

      <p className="mt-8 rounded-2xl bg-cream-deep/50 p-5 text-sm text-ink-soft">{blocks.note}</p>
    </div>
  );
}
