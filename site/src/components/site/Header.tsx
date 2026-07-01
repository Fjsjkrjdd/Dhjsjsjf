"use client";

import { useState } from "react";
import Link from "next/link";
import { PhoneIcon } from "@/components/icons";
import { telHref } from "@/lib/socials";

const NAV = [
  { href: "/", label: "Главная" },
  { href: "/#about", label: "Обо мне" },
  { href: "/#services", label: "Услуги" },
  { href: "/#approach", label: "Мой подход" },
  { href: "/#first-meeting", label: "Первая встреча" },
  { href: "/#contacts", label: "Контакты" },
];

export default function Header({
  logoText,
  phone,
}: {
  logoText: string;
  phone: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-[#e1d4c4] bg-[#f7f2eb]/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2"
          onClick={() => setOpen(false)}
        >
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#2f2d2b] text-lg font-semibold text-white font-[family-name:var(--font-display)]">
            Н
          </span>
          <span className="font-[family-name:var(--font-display)] text-lg font-semibold text-ink">
            {logoText}
          </span>
        </Link>

        <nav className="hidden items-center gap-6 lg:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm font-medium text-ink-soft transition hover:text-[#9b7b62]"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-4 lg:flex">
          <a
            href={telHref(phone)}
            className="flex items-center gap-2 text-sm font-semibold text-ink hover:text-[#9b7b62]"
          >
            <PhoneIcon className="h-4 w-4" />
            {phone}
          </a>
          <Link
            href="/booking"
            className="rounded-full bg-[#2f2d2b] px-5 py-2 text-sm font-semibold text-white transition hover:bg-[#9b7b62]"
          >
            Записаться
          </Link>
        </div>

        <button
          type="button"
          aria-label="Меню"
          onClick={() => setOpen((v) => !v)}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-ink lg:hidden"
        >
          <svg
            viewBox="0 0 24 24"
            className="h-6 w-6"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
          >
            {open ? (
              <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
            ) : (
              <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
            )}
          </svg>
        </button>
      </div>

      {open && (
        <div className="border-t border-cream-deep bg-cream lg:hidden">
          <nav className="mx-auto flex max-w-6xl flex-col px-4 py-3 sm:px-6">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="border-b border-cream-deep py-3 text-base font-medium text-ink"
              >
                {item.label}
              </Link>
            ))}
            <div className="flex flex-col gap-3 pt-4">
              <a
                href={telHref(phone)}
                className="flex items-center gap-2 font-semibold text-ink"
              >
                <PhoneIcon className="h-4 w-4" /> {phone}
              </a>
              <Link
                href="/booking"
                onClick={() => setOpen(false)}
                className="rounded-full bg-[#2f2d2b] px-5 py-2.5 text-center text-sm font-semibold text-white"
              >
                Записаться на консультацию
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
