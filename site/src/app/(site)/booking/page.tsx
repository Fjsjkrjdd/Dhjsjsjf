import type { Metadata } from "next";
import { prisma } from "@/lib/prisma";
import { getSettings, getBlocks } from "@/lib/content";
import { isPaymentsConfigured } from "@/lib/yookassa";
import { telHref } from "@/lib/socials";
import BookingForm from "@/components/site/BookingForm";
import { PhoneIcon, MapPinIcon, ClockIcon, CheckIcon } from "@/components/icons";
import { BLOCK_DEFAULTS } from "@/lib/blockDefaults";

export const metadata: Metadata = { title: "Запись на консультацию" };
export const dynamic = "force-dynamic";

type SearchParams = Promise<{ service?: string }>;

export default async function BookingPage({ searchParams }: { searchParams: SearchParams }) {
  const { service: serviceSlug } = await searchParams;
  const [settings, blocks, services] = await Promise.all([
    getSettings(),
    getBlocks("booking", BLOCK_DEFAULTS.booking.blocks),
    prisma.service.findMany({ where: { isActive: true, isBookable: true }, orderBy: { order: "asc" } }),
  ]);
  const paymentsEnabled = isPaymentsConfigured(settings);

  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6 md:py-20">
      <h1 className="text-4xl text-ink sm:text-5xl">{blocks.title}</h1>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">{blocks.subtitle}</p>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_320px]">
        <BookingForm
          services={services}
          defaultSlug={serviceSlug}
          paymentsEnabled={paymentsEnabled}
        />

        <aside className="space-y-6">
          <div className="rounded-2xl border border-cream-deep bg-white p-6 shadow-sm">
            <h2 className="text-lg text-ink">Контакты</h2>
            <ul className="mt-4 space-y-3 text-sm text-ink-soft">
              <li className="flex items-start gap-3">
                <PhoneIcon className="mt-0.5 h-4 w-4 shrink-0 text-sage" />
                <a href={telHref(settings.phone)} className="hover:text-sage-dark">{settings.phone}</a>
              </li>
              <li className="flex items-start gap-3">
                <MapPinIcon className="mt-0.5 h-4 w-4 shrink-0 text-sage" />
                <span>{settings.address}</span>
              </li>
              <li className="flex items-start gap-3">
                <ClockIcon className="mt-0.5 h-4 w-4 shrink-0 text-sage" />
                <span>{settings.workingHours}</span>
              </li>
            </ul>
          </div>

          <div className="rounded-2xl bg-sage-light p-6">
            <ul className="space-y-3 text-sm text-ink">
              {[blocks.benefit_1, blocks.benefit_2, blocks.benefit_3].map((b, i) => (
                <li key={i} className="flex items-start gap-2.5">
                  <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-sage-dark" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
