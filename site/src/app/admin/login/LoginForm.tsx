"use client";

import { useActionState } from "react";
import { loginAction } from "../_actions/auth";

export default function LoginForm() {
  const [state, action, pending] = useActionState(loginAction, undefined);
  const field =
    "w-full rounded-xl border border-cream-deep bg-white px-4 py-3 text-ink outline-none transition focus:border-sage focus:ring-2 focus:ring-sage-light";

  return (
    <form action={action} className="mt-8 space-y-4 rounded-2xl border border-cream-deep bg-white p-6 shadow-sm">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-ink">E-mail</label>
        <input name="email" type="email" required autoComplete="username" className={field} placeholder="admin@chernova-psy.ru" />
      </div>
      <div>
        <label className="mb-1.5 block text-sm font-medium text-ink">Пароль</label>
        <input name="password" type="password" required autoComplete="current-password" className={field} placeholder="••••••••" />
      </div>
      {state?.error && <p className="text-sm font-medium text-terracotta-dark">{state.error}</p>}
      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-full bg-sage px-6 py-3 text-sm font-semibold text-white transition hover:bg-sage-dark disabled:opacity-60"
      >
        {pending ? "Вход…" : "Войти"}
      </button>
    </form>
  );
}
