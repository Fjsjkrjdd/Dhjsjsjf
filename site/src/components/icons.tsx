import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const base = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  viewBox: "0 0 24 24",
};

export function UserIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6" />
    </svg>
  );
}
export function UsersIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M2.5 20c0-3 3-5.2 6.5-5.2s6.5 2.2 6.5 5.2" />
      <path d="M16 5.5a3 3 0 0 1 0 5.8M17.5 14.6c2.4.6 4 2.4 4 5.4" />
    </svg>
  );
}
export function PaletteIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3a9 9 0 1 0 0 18c1.7 0 2-1.3 1.2-2.2-.8-.9-.5-2.3.9-2.3H17a4 4 0 0 0 4-4c0-4.7-4-9.5-9-9.5Z" />
      <circle cx="7.5" cy="11" r="1" />
      <circle cx="10" cy="7" r="1" />
      <circle cx="14.5" cy="7.5" r="1" />
    </svg>
  );
}
export function SparklesIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3Z" />
      <path d="M18 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2Z" />
    </svg>
  );
}
export function VideoIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <rect x="2.5" y="6" width="13" height="12" rx="2" />
      <path d="M15.5 10l6-3v10l-6-3" />
    </svg>
  );
}
export function HeartIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 20s-7-4.4-9.2-9C1.4 8 2.8 4.8 6 4.8c2 0 3.2 1.2 4 2.4.8-1.2 2-2.4 4-2.4 3.2 0 4.6 3.2 3.2 6.2C19 15.6 12 20 12 20Z" />
    </svg>
  );
}
export function PhoneIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M5 3.5h3.2l1.4 4-2 1.3a12 12 0 0 0 5.1 5.1l1.3-2 4 1.4V20a1.5 1.5 0 0 1-1.6 1.5C9.9 21 3 14.1 3 5.1A1.5 1.5 0 0 1 4.5 3.5Z" />
    </svg>
  );
}
export function MapPinIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11Z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}
export function ClockIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}
export function CheckIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M4 12.5l5 5 11-11" />
    </svg>
  );
}
export function ArrowRightIcon(props: IconProps) {
  return (
    <svg {...base} {...props}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}
export function StarIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.9 6.1 21l1.2-6.5L2.5 9.4l6.6-.9L12 2.5Z" />
    </svg>
  );
}

const ICONS: Record<string, (p: IconProps) => React.JSX.Element> = {
  user: UserIcon,
  users: UsersIcon,
  palette: PaletteIcon,
  sparkles: SparklesIcon,
  video: VideoIcon,
  heart: HeartIcon,
};

export function ServiceIcon({ name, ...props }: IconProps & { name?: string }) {
  const Cmp = ICONS[name || "heart"] || HeartIcon;
  return <Cmp {...props} />;
}
