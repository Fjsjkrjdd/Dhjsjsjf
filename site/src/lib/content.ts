import { prisma } from "./prisma";
import type { SiteSettings } from "@prisma/client";

/** Get (or lazily create) the singleton site settings record. */
export async function getSettings(): Promise<SiteSettings> {
  let settings = await prisma.siteSettings.findUnique({ where: { id: 1 } });
  if (!settings) {
    settings = await prisma.siteSettings.create({ data: { id: 1 } });
  }
  return settings;
}

/**
 * Returns a map of content blocks for a given page: { key: value }.
 * Missing keys fall back to the provided defaults (and are created lazily
 * so they appear in the admin editor).
 */
export async function getBlocks(
  page: string,
  defaults: Record<string, { value: string; label: string; type?: string }>,
): Promise<Record<string, string>> {
  const existing = await prisma.contentBlock.findMany({ where: { page } });
  const map: Record<string, string> = {};
  const existingKeys = new Set(existing.map((b) => b.key));

  for (const block of existing) {
    map[block.key] = block.value;
  }

  // Lazily create any missing default blocks so editors can find them.
  const toCreate = Object.entries(defaults).filter(([key]) => !existingKeys.has(key));
  if (toCreate.length > 0) {
    await prisma.$transaction(
      toCreate.map(([key, def]) =>
        prisma.contentBlock.create({
          data: {
            page,
            key,
            value: def.value,
            label: def.label,
            type: def.type ?? "text",
          },
        }),
      ),
    );
    for (const [key, def] of toCreate) {
      map[key] = def.value;
    }
  }

  // Ensure every default key is present in the returned map.
  for (const [key, def] of Object.entries(defaults)) {
    if (!(key in map)) map[key] = def.value;
  }

  return map;
}

export function formatPrice(price: number): string {
  return new Intl.NumberFormat("ru-RU").format(price);
}
