"use client";

import { useState } from "react";

export default function ImagePicker({
  name,
  label,
  current,
  hint,
}: {
  name: string; // file input name; a hidden field `${base}` keeps current value
  label: string;
  current?: string | null;
  hint?: string;
}) {
  const [preview, setPreview] = useState<string | null>(current || null);

  return (
    <div>
      <span className="mb-1.5 block text-sm font-medium text-ink">{label}</span>
      <div className="flex items-center gap-4">
        <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg border border-cream-deep bg-cream-deep/40">
          {preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="flex h-full w-full items-center justify-center text-xs text-ink-soft">нет</span>
          )}
        </div>
        <div className="flex-1">
          <input
            type="file"
            name={name}
            accept="image/*"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) setPreview(URL.createObjectURL(f));
            }}
            className="block w-full text-sm text-ink-soft file:mr-3 file:rounded-full file:border-0 file:bg-sage file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-sage-dark"
          />
          {hint ? <p className="mt-1 text-xs text-ink-soft">{hint}</p> : null}
        </div>
      </div>
    </div>
  );
}
