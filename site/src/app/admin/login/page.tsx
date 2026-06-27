import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import LoginForm from "./LoginForm";

export const metadata: Metadata = { title: "Вход в админ-панель" };

export default async function LoginPage() {
  const session = await getSession();
  if (session) redirect("/admin");

  return (
    <div className="flex min-h-screen items-center justify-center bg-cream px-4">
      <div className="w-full max-w-sm">
        <div className="text-center">
          <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-sage text-2xl font-semibold text-white font-[family-name:var(--font-display)]">
            Н
          </span>
          <h1 className="mt-4 text-2xl text-ink">Админ-панель</h1>
          <p className="mt-1 text-sm text-ink-soft">Управление сайтом психолога</p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
