import Link from "next/link";
import type { SocialLink } from "@/lib/socials";
import {
  VkIcon,
  TelegramIcon,
  WhatsAppIcon,
  InstagramIcon,
  YoutubeIcon,
  YandexIcon,
} from "./SocialIcons";

const ICONS: Record<string, (p: { className?: string }) => React.JSX.Element> = {
  vk: VkIcon,
  telegram: TelegramIcon,
  whatsapp: WhatsAppIcon,
  instagram: InstagramIcon,
  youtube: YoutubeIcon,
  yandex: YandexIcon,
};

export default function SocialBar({
  links,
  className = "",
  iconClassName = "h-5 w-5",
}: {
  links: SocialLink[];
  className?: string;
  iconClassName?: string;
}) {
  if (links.length === 0) return null;
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {links.map((l) => {
        const Icon = ICONS[l.key] || YandexIcon;
        return (
          <Link
            key={l.key}
            href={l.href}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={l.label}
            title={l.label}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-sage-light text-sage-dark transition hover:bg-sage hover:text-white"
          >
            <Icon className={iconClassName} />
          </Link>
        );
      })}
    </div>
  );
}
