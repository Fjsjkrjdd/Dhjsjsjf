import Link from "next/link";
import type { SiteSettings } from "@prisma/client";
import { getSocialLinks, telHref } from "@/lib/socials";
import { PhoneIcon, MapPinIcon, ClockIcon } from "@/components/icons";
import SocialBar from "./SocialBar";

export default function Footer({ settings }: { settings: SiteSettings }) {
  const socials = getSocialLinks(settings);
  const year = new Date().getFullYear();

  return (
    <footer className="mt-auto bg-ink text-cream">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-3">
        <div>
          <p className="font-[family-name:var(--font-display)] text-2xl font-semibold">
            {settings.ownerName}
          </p>
          <p className="mt-2 text-sm text-cream/70">{settings.profession}</p>
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-cream/70">
            {settings.tagline}
          </p>
          <SocialBar links={socials} className="mt-5" />
        </div>

        <div>
          <h3 className="text-base font-semibold text-cream">Контакты</h3>
          <ul className="mt-4 space-y-3 text-sm text-cream/80">
            <li className="flex items-start gap-3">
              <PhoneIcon className="mt-0.5 h-4 w-4 shrink-0 text-sage" />
              <a href={telHref(settings.phone)} className="hover:text-white">
                {settings.phone}
              </a>
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

        <div>
          <h3 className="text-base font-semibold text-cream">Разделы</h3>
          <ul className="mt-4 space-y-2 text-sm text-cream/80">
            <li><Link href="/services" className="hover:text-white">Услуги и цены</Link></li>
            <li><Link href="/about" className="hover:text-white">Обо мне и образование</Link></li>
            <li><Link href="/reviews" className="hover:text-white">Отзывы</Link></li>
            <li><Link href="/articles" className="hover:text-white">Статьи</Link></li>
            <li><Link href="/contacts" className="hover:text-white">Контакты</Link></li>
            <li><Link href="/booking" className="hover:text-white">Запись и оплата</Link></li>
          </ul>
        </div>
      </div>

      <div className="border-t border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-xs text-cream/60 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>© {year} {settings.siteName}. Все права защищены.</span>
          <div className="flex gap-4">
            <Link href="/privacy" className="hover:text-white">Политика конфиденциальности</Link>
            <Link href="/admin" className="hover:text-white">Вход в админку</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
