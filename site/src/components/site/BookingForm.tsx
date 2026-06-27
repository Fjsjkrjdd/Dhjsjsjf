"use client";

import { useState } from "react";
import { formatPrice } from "@/lib/content";

export type BookingService = {
  slug: string;
  title: string;
  price: number;
  duration: string;
  isBookable: boolean;
};

export default function BookingForm({
  services,
  defaultSlug,
  paymentsEnabled,
}: {
  services: BookingService[];
  defaultSlug?: string;
  paymentsEnabled: boolean;
}) {
  const initial = services.find((s) => s.slug === defaultSlug) ?? services[0];
  const [slug, setSlug] = useState(initial?.slug ?? "");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [preferredDate, setPreferredDate] = useState("");
  const [comment, setComment] = useState("");
  const [payOnline, setPayOnline] = useState(false);
  const [agree, setAgree] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  const selected = services.find((s) => s.slug === slug);
  const canPay = paymentsEnabled && !!selected && selected.price > 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!agree) {
      setMessage("Необходимо согласие на обработку персональных данных.");
      setStatus("error");
      return;
    }
    setStatus("loading");
    setMessage("");
    try {
      const res = await fetch("/api/booking", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          serviceSlug: slug,
          name,
          phone,
          email,
          preferredDate,
          comment,
          pay: canPay && payOnline,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus("error");
        setMessage(data.error || "Не удалось отправить заявку. Попробуйте позже.");
        return;
      }
      if (data.paymentUrl) {
        window.location.href = data.paymentUrl;
        return;
      }
      setStatus("done");
      setMessage(data.message || "Спасибо! Ваша заявка принята. Я свяжусь с вами в ближайшее время.");
    } catch {
      setStatus("error");
      setMessage("Ошибка сети. Попробуйте позже.");
    }
  }

  if (status === "done") {
    return (
      <div className="rounded-2xl border border-sage bg-sage-light p-8 text-center">
        <h3 className="text-2xl text-ink">Заявка отправлена</h3>
        <p className="mt-3 text-ink-soft">{message}</p>
      </div>
    );
  }

  const field =
    "w-full rounded-xl border border-cream-deep bg-white px-4 py-3 text-ink outline-none transition focus:border-sage focus:ring-2 focus:ring-sage-light";

  return (
    <form onSubmit={submit} className="space-y-4 rounded-2xl border border-cream-deep bg-white p-6 shadow-sm sm:p-8">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-ink">Услуга</label>
        <select value={slug} onChange={(e) => setSlug(e.target.value)} className={field}>
          {services.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.title}
              {s.price > 0 ? ` — ${formatPrice(s.price)} ₽` : ""}
              {s.duration ? ` (${s.duration})` : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink">Ваше имя *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required className={field} placeholder="Имя" />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink">Телефон *</label>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} required type="tel" className={field} placeholder="+7 (___) ___-__-__" />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink">E-mail</label>
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" className={field} placeholder="email@example.com" />
        </div>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-ink">Удобная дата / время</label>
          <input value={preferredDate} onChange={(e) => setPreferredDate(e.target.value)} className={field} placeholder="Например, будни после 18:00" />
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-ink">Комментарий</label>
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3} className={field} placeholder="Кратко опишите ваш запрос (по желанию)" />
      </div>

      {canPay && (
        <label className="flex items-start gap-3 rounded-xl bg-cream-deep/50 p-4">
          <input type="checkbox" checked={payOnline} onChange={(e) => setPayOnline(e.target.checked)} className="mt-1 h-4 w-4 accent-[var(--color-sage)]" />
          <span className="text-sm text-ink-soft">
            Оплатить онлайн картой ({selected ? `${formatPrice(selected.price)} ₽` : ""}). Вы будете перенаправлены на защищённую страницу оплаты. Чек придёт на e-mail.
          </span>
        </label>
      )}

      <label className="flex items-start gap-3 text-sm text-ink-soft">
        <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 h-4 w-4 accent-[var(--color-sage)]" />
        <span>
          Я согласен(а) на обработку персональных данных в соответствии с{" "}
          <a href="/privacy" className="text-sage-dark underline">политикой конфиденциальности</a>.
        </span>
      </label>

      {status === "error" && <p className="text-sm font-medium text-terracotta-dark">{message}</p>}

      <button
        type="submit"
        disabled={status === "loading"}
        className="w-full rounded-full bg-sage px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-sage-dark disabled:opacity-60"
      >
        {status === "loading"
          ? "Отправляем…"
          : canPay && payOnline
            ? "Перейти к оплате"
            : "Отправить заявку"}
      </button>
    </form>
  );
}
