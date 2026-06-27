import Link from "next/link";
import { ServiceIcon, ArrowRightIcon } from "@/components/icons";
import { formatPrice } from "@/lib/content";

export type ServiceCardData = {
  slug: string;
  title: string;
  shortDescription: string;
  price: number;
  oldPrice?: number | null;
  priceSuffix?: string;
  duration: string;
  icon: string;
};

export default function ServiceCard({ service }: { service: ServiceCardData }) {
  return (
    <div className="group flex flex-col rounded-2xl border border-cream-deep bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-sage-light text-sage-dark">
        <ServiceIcon name={service.icon} className="h-6 w-6" />
      </div>
      <h3 className="mt-5 text-xl text-ink">{service.title}</h3>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-ink-soft">
        {service.shortDescription}
      </p>
      <div className="mt-5 flex items-end justify-between border-t border-cream-deep pt-4">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-ink">
              {formatPrice(service.price)} ₽
            </span>
            {service.oldPrice ? (
              <span className="text-sm text-ink-soft line-through">
                {formatPrice(service.oldPrice)} ₽
              </span>
            ) : null}
          </div>
          {service.duration ? (
            <span className="text-xs text-ink-soft">{service.duration}</span>
          ) : null}
        </div>
        <Link
          href={`/booking?service=${service.slug}`}
          className="inline-flex items-center gap-1 rounded-full bg-sage px-4 py-2 text-sm font-semibold text-white transition hover:bg-sage-dark"
        >
          Записаться
          <ArrowRightIcon className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}
