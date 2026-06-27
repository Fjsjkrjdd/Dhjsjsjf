import type { Metadata } from "next";
import { getSession } from "@/lib/auth";
import { changePassword } from "../../_actions/cms";
import { PageHeader, Card, Field, SaveButton, Toast } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Мой профиль" };

type SP = Promise<{ saved?: string; error?: string }>;

export default async function AccountPage({ searchParams }: { searchParams: SP }) {
  const { saved, error } = await searchParams;
  const session = await getSession();

  return (
    <div>
      <PageHeader title="Мой профиль" description="Данные для входа в админ-панель." />
      <Toast show={!!saved}>Пароль изменён.</Toast>
      {error === "current" && <Toast show><span className="text-terracotta-dark">Неверный текущий пароль.</span></Toast>}
      {error === "short" && <Toast show><span className="text-terracotta-dark">Новый пароль должен быть не короче 6 символов.</span></Toast>}

      <Card className="mb-6">
        <p className="text-sm text-ink-soft">E-mail для входа</p>
        <p className="text-lg font-semibold text-ink">{session?.email}</p>
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-semibold text-ink">Сменить пароль</h2>
        <form action={changePassword} className="max-w-md space-y-4">
          <Field label="Текущий пароль" name="current" type="password" required />
          <Field label="Новый пароль" name="next" type="password" required hint="Минимум 6 символов" />
          <SaveButton>Обновить пароль</SaveButton>
        </form>
      </Card>
    </div>
  );
}
