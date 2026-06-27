"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { logoutAction } from "../_actions/auth";

const LINKS = [
  { href: "/admin", label: "Обзор", exact: true },
  { href: "/admin/content", label: "Тексты страниц" },
  { href: "/admin/services", label: "Услуги и цены" },
  { href: "/admin/diplomas", label: "Дипломы" },
  { href: "/admin/education", label: "Образование" },
  { href: "/admin/reviews", label: "Отзывы" },
  { href: "/admin/articles", label: "Статьи" },
  { href: "/admin/pages", label: "Страницы" },
  { href: "/admin/orders", label: "Заявки и оплаты" },
  { href: "/admin/settings", label: "Настройки сайта" },
  { href: "/admin/account", label: "Мой профиль" },
];

export default function AdminNav({ userName }: { userName: string }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(href + "/");

  return (
    <>
      {/* Mobile top bar */}
      <div className="flex items-center justify-between border-b border-cream-deep bg-white px-4 py-3 lg:hidden">
        <span className="font-semibold text-ink">Админ-панель</span>
        <button onClick={() => setOpen((v) => !v)} aria-label="Меню" className="rounded-lg p-2 text-ink">
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <aside
        className={`${open ? "block" : "hidden"} border-b border-cream-deep bg-white lg:sticky lg:top-0 lg:block lg:h-screen lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r`}
      >
        <div className="flex h-full flex-col p-4">
          <Link href="/admin" className="hidden items-center gap-2 px-2 py-3 lg:flex">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-sage font-semibold text-white">Н</span>
            <span className="font-[family-name:var(--font-display)] text-lg font-semibold text-ink">CMS</span>
          </Link>
          <nav className="mt-2 flex flex-1 flex-col gap-0.5">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className={`rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  isActive(l.href, l.exact)
                    ? "bg-sage text-white"
                    : "text-ink-soft hover:bg-cream-deep/60 hover:text-ink"
                }`}
              >
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="mt-4 border-t border-cream-deep pt-4">
            <Link href="/" target="_blank" className="block rounded-lg px-3 py-2 text-sm text-sage-dark hover:bg-cream-deep/60">
              Открыть сайт ↗
            </Link>
            <p className="mt-2 px-3 text-xs text-ink-soft">{userName}</p>
            <form action={logoutAction}>
              <button className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm text-terracotta-dark hover:bg-cream-deep/60">
                Выйти
              </button>
            </form>
          </div>
        </div>
      </aside>
    </>
  );
}
