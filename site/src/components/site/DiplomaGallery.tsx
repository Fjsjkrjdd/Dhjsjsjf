"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import Image from "next/image";

export type DiplomaItem = {
  id: string;
  title: string;
  description: string;
  image: string;
};

export default function DiplomaGallery({ items }: { items: DiplomaItem[] }) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<number | null>(null);

  const scrollBy = useCallback((dir: 1 | -1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * (el.clientWidth * 0.8), behavior: "smooth" });
  }, []);

  const close = useCallback(() => setActive(null), []);
  const next = useCallback(
    () => setActive((i) => (i === null ? i : (i + 1) % items.length)),
    [items.length],
  );
  const prev = useCallback(
    () => setActive((i) => (i === null ? i : (i - 1 + items.length) % items.length)),
    [items.length],
  );

  useEffect(() => {
    if (active === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") prev();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [active, close, next, prev]);

  if (items.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-cream-deep bg-cream-deep/40 p-8 text-center text-ink-soft">
        Дипломы и сертификаты пока не загружены. Добавьте их в админ-панели.
      </p>
    );
  }

  return (
    <div className="relative">
      {/* Arrows (desktop) */}
      {items.length > 1 && (
        <>
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            aria-label="Назад"
            className="absolute -left-3 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-white p-2 text-ink shadow-md transition hover:bg-sage hover:text-white md:flex"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <path d="M15 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            aria-label="Вперёд"
            className="absolute -right-3 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-white p-2 text-ink shadow-md transition hover:bg-sage hover:text-white md:flex"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </>
      )}

      <div
        ref={scrollerRef}
        className="no-scrollbar flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2"
      >
        {items.map((item, i) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setActive(i)}
            className="group relative aspect-[3/4] w-44 shrink-0 snap-start overflow-hidden rounded-xl border border-cream-deep bg-white shadow-sm transition hover:shadow-lg sm:w-52"
            title={item.title}
          >
            <Image
              src={item.image}
              alt={item.title}
              fill
              sizes="220px"
              className="object-cover transition duration-300 group-hover:scale-105"
            />
            <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-3 text-left text-xs font-medium text-white">
              {item.title}
            </span>
            <span className="absolute right-2 top-2 rounded-full bg-white/85 p-1.5 text-ink opacity-0 transition group-hover:opacity-100">
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8}>
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-3.5-3.5M11 8v6M8 11h6" strokeLinecap="round" />
              </svg>
            </span>
          </button>
        ))}
      </div>

      {/* Lightbox */}
      {active !== null && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/85 p-4"
          onClick={close}
        >
          <button
            type="button"
            onClick={close}
            aria-label="Закрыть"
            className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/25"
          >
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
            </svg>
          </button>

          {items.length > 1 && (
            <>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); prev(); }}
                aria-label="Назад"
                className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white transition hover:bg-white/25"
              >
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={1.8}>
                  <path d="M15 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); next(); }}
                aria-label="Вперёд"
                className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white transition hover:bg-white/25"
              >
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={1.8}>
                  <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </>
          )}

          <figure
            className="flex max-h-[88vh] max-w-3xl flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative h-[78vh] w-full">
              <Image
                src={items[active].image}
                alt={items[active].title}
                fill
                sizes="90vw"
                className="object-contain"
              />
            </div>
            <figcaption className="mt-3 max-w-xl text-center text-sm text-white/90">
              <span className="font-semibold">{items[active].title}</span>
              {items[active].description ? ` — ${items[active].description}` : ""}
            </figcaption>
          </figure>
        </div>
      )}
    </div>
  );
}
