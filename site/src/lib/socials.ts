import type { SiteSettings } from "@prisma/client";

export type SocialLink = {
  key: string;
  label: string;
  href: string;
};

/** Build the list of configured social links from site settings. */
export function getSocialLinks(s: SiteSettings): SocialLink[] {
  const links: SocialLink[] = [];
  if (s.vk) links.push({ key: "vk", label: "ВКонтакте", href: s.vk });
  if (s.telegram) links.push({ key: "telegram", label: "Telegram", href: normalizeTelegram(s.telegram) });
  if (s.whatsapp) links.push({ key: "whatsapp", label: "WhatsApp", href: normalizeWhatsApp(s.whatsapp) });
  if (s.instagram) links.push({ key: "instagram", label: "Instagram", href: s.instagram });
  if (s.youtube) links.push({ key: "youtube", label: "YouTube", href: s.youtube });
  if (s.yandexMaps) links.push({ key: "yandex", label: "Яндекс Карты", href: s.yandexMaps });
  return links;
}

function normalizeTelegram(value: string): string {
  if (value.startsWith("http")) return value;
  return `https://t.me/${value.replace(/^@/, "")}`;
}

function normalizeWhatsApp(value: string): string {
  if (value.startsWith("http")) return value;
  return `https://wa.me/${value.replace(/[^0-9]/g, "")}`;
}

export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^0-9+]/g, "")}`;
}
