import type { Metadata } from "next";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { getSettings, getBlocks } from "@/lib/content";
import ReviewCard from "@/components/site/ReviewCard";
import { BLOCK_DEFAULTS } from "@/lib/blockDefaults";

export const metadata: Metadata = { title: "Отзывы" };
export const dynamic = "force-dynamic";

export default async function ReviewsPage() {
  const [blocks, reviews, settings] = await Promise.all([
    getBlocks("reviews", BLOCK_DEFAULTS.reviews.blocks),
    prisma.review.findMany({ where: { isPublished: true }, orderBy: { order: "asc" } }),
    getSettings(),
  ]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 md:py-20">
      <h1 className="text-4xl text-ink sm:text-5xl">{blocks.title}</h1>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">{blocks.subtitle}</p>

      {reviews.length === 0 ? (
        <p className="mt-12 rounded-2xl border border-dashed border-cream-deep p-8 text-center text-ink-soft">
          Отзывы пока не добавлены.
        </p>
      ) : (
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {reviews.map((r) => (
            <ReviewCard key={r.id} review={r} />
          ))}
        </div>
      )}

      {settings.yandexMaps && (
        <div className="mt-12 text-center">
          <Link
            href={settings.yandexMaps}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex rounded-full border border-sage px-6 py-3 text-sm font-semibold text-sage-dark transition hover:bg-sage-light"
          >
            Смотреть отзывы на Яндекс Картах
          </Link>
        </div>
      )}
    </div>
  );
}
