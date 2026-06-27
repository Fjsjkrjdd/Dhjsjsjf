import { StarIcon } from "@/components/icons";

export type ReviewData = {
  id: string;
  author: string;
  text: string;
  rating: number;
  source?: string;
};

export default function ReviewCard({ review }: { review: ReviewData }) {
  return (
    <figure className="flex h-full flex-col rounded-2xl border border-cream-deep bg-white p-6 shadow-sm">
      <div className="flex gap-0.5 text-terracotta">
        {Array.from({ length: 5 }).map((_, i) => (
          <StarIcon
            key={i}
            className={`h-4 w-4 ${i < review.rating ? "text-terracotta" : "text-cream-deep"}`}
          />
        ))}
      </div>
      <blockquote className="mt-4 flex-1 text-sm leading-relaxed text-ink-soft">
        “{review.text}”
      </blockquote>
      <figcaption className="mt-5 border-t border-cream-deep pt-4">
        <span className="font-semibold text-ink">{review.author}</span>
        {review.source ? (
          <span className="ml-2 text-xs text-ink-soft">· {review.source}</span>
        ) : null}
      </figcaption>
    </figure>
  );
}
