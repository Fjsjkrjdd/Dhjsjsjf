import Link from "next/link";

export const fieldClass =
  "w-full rounded-lg border border-cream-deep bg-white px-3.5 py-2.5 text-sm text-ink outline-none transition focus:border-sage focus:ring-2 focus:ring-sage-light";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold text-ink">{title}</h1>
        {description ? <p className="mt-1 text-sm text-ink-soft">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-cream-deep bg-white p-5 shadow-sm sm:p-6 ${className}`}>
      {children}
    </div>
  );
}

export function Field({
  label,
  name,
  defaultValue,
  type = "text",
  placeholder,
  required,
  hint,
}: {
  label: string;
  name: string;
  defaultValue?: string | number | null;
  type?: string;
  placeholder?: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}{required ? " *" : ""}</span>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue ?? undefined}
        placeholder={placeholder}
        required={required}
        className={fieldClass}
      />
      {hint ? <span className="mt-1 block text-xs text-ink-soft">{hint}</span> : null}
    </label>
  );
}

export function TextArea({
  label,
  name,
  defaultValue,
  rows = 4,
  placeholder,
  hint,
}: {
  label: string;
  name: string;
  defaultValue?: string | null;
  rows?: number;
  placeholder?: string;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      <textarea
        name={name}
        rows={rows}
        defaultValue={defaultValue ?? undefined}
        placeholder={placeholder}
        className={fieldClass}
      />
      {hint ? <span className="mt-1 block text-xs text-ink-soft">{hint}</span> : null}
    </label>
  );
}

export function Checkbox({ label, name, defaultChecked }: { label: string; name: string; defaultChecked?: boolean }) {
  return (
    <label className="flex items-center gap-2.5 text-sm text-ink">
      <input type="checkbox" name={name} defaultChecked={defaultChecked} className="h-4 w-4 accent-[var(--color-sage)]" />
      {label}
    </label>
  );
}

export function SaveButton({ children = "Сохранить" }: { children?: React.ReactNode }) {
  return (
    <button
      type="submit"
      className="rounded-full bg-sage px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-sage-dark"
    >
      {children}
    </button>
  );
}

export function LinkButton({ href, children, variant = "primary" }: { href: string; children: React.ReactNode; variant?: "primary" | "ghost" }) {
  const cls =
    variant === "primary"
      ? "bg-sage text-white hover:bg-sage-dark"
      : "border border-cream-deep text-ink hover:bg-cream-deep/60";
  return (
    <Link href={href} className={`inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-sm font-semibold transition ${cls}`}>
      {children}
    </Link>
  );
}

export function Toast({ show, children }: { show: boolean; children: React.ReactNode }) {
  if (!show) return null;
  return (
    <div className="mb-5 rounded-lg border border-sage bg-sage-light px-4 py-3 text-sm font-medium text-sage-dark">
      {children}
    </div>
  );
}
