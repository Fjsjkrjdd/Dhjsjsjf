import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import AdminNav from "./AdminNav";

export const dynamic = "force-dynamic";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getSession();
  if (!session) redirect("/admin/login");

  return (
    <div className="min-h-screen bg-cream lg:flex">
      <AdminNav userName={session.name || session.email} />
      <div className="flex-1">
        <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-10">{children}</div>
      </div>
    </div>
  );
}
