"use server";

import { redirect } from "next/navigation";
import { authenticate, createSession, destroySession } from "@/lib/auth";

export async function loginAction(_prev: { error?: string } | undefined, formData: FormData) {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  if (!email || !password) {
    return { error: "Введите e-mail и пароль" };
  }

  const user = await authenticate(email, password);
  if (!user) {
    return { error: "Неверный e-mail или пароль" };
  }

  await createSession({
    userId: user.id,
    email: user.email,
    name: user.name,
    role: user.role,
  });
  redirect("/admin");
}

export async function logoutAction() {
  await destroySession();
  redirect("/admin/login");
}
