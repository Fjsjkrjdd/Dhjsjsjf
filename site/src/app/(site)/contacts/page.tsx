import type { Metadata } from "next";
import Link from "next/link";
import { getSettings, getBlocks } from "@/lib/content";
import { getSocialLinks, telHref } from "@/lib/socials";
import SocialBar from "@/components/site/SocialBar";
import { PhoneIcon, MapPinIcon, ClockIcon } from "@/components/icons";
import { BLOCK_DEFAULTS } from "@/lib/blockDefaults";

export const metadata: Metadata = { title: "Контакты" };
export const dynamic = "force-dynamic";

export default async function ContactsPage() {
  const [settings, blocks] = await Promise.all([getSettings(), getBlocks("contacts", BLOCK_DEFAULTS.contacts.blocks)]);
  const socials = getSocialLinks(settings);

  return (
    <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 md:py-20">
      <h1 className="text-4xl text-ink sm:text-5xl">{blocks.title}</h1>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">{blocks.subtitle}</p>

      <div className="mt-10 grid gap-8 lg:grid-cols-[360px_1fr]">
        <div className="space-y-6">
          <div className="rounded-2xl border border-cream-deep bg-white p-6 shadow-sm">
            <ul className="space-y-4 text-ink-soft">
              <li className="flex items-start gap-3">
                <PhoneIcon className="mt-0.5 h-5 w-5 shrink-0 text-sage" />
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-soft">Телефон</p>
                  <a href={telHref(settings.phone)} className="text-lg font-semibold text-ink hover:text-sage-dark">
                    {settings.phone}
                  </a>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <MapPinIcon className="mt-0.5 h-5 w-5 shrink-0 text-sage" />
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-soft">Адрес</p>
                  <p className="font-medium text-ink">{settings.address}</p>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <ClockIcon className="mt-0.5 h-5 w-5 shrink-0 text-sage" />
                <div>
                  <p className="text-xs uppercase tracking-wide text-ink-soft">Время работы</p>
                  <p className="font-medium text-ink">{settings.workingHours}</p>
                </div>
              </li>
            </ul>
            {settings.email ? (
              <a href={`mailto:${settings.email}`} className="mt-4 block text-sm text-sage-dark hover:underline">
                {settings.email}
              </a>
            ) : null}
            <SocialBar links={socials} className="mt-5" />
          </div>

          <Link
            href="/booking"
            className="block rounded-2xl bg-sage p-6 text-center text-white transition hover:bg-sage-dark"
          >
            <span className="text-lg font-semibold">Записаться на консультацию</span>
            <span className="mt-1 block text-sm text-white/80">Очно или онлайн</span>
          </Link>
        </div>

        <div className="min-h-[360px] overflow-hidden rounded-2xl border border-cream-deep bg-white shadow-sm">
          {settings.mapEmbed ? (
            <div className="h-full w-full [&>iframe]:h-full [&>iframe]:w-full" dangerouslySetInnerHTML={{ __html: settings.mapEmbed }} />
          ) : (
            <div className="flex h-full min-h-[360px] flex-col items-center justify-center gap-4 p-8 text-center">
              <MapPinIcon className="h-12 w-12 text-sage" />
              <p className="text-ink-soft">{settings.address}</p>
              {settings.yandexMaps && (
                <Link
                  href={settings.yandexMaps}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-full border border-sage px-6 py-2.5 text-sm font-semibold text-sage-dark transition hover:bg-sage-light"
                >
                  Открыть на Яндекс Картах
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
