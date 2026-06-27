import type { Metadata } from "next";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { getBlocks } from "@/lib/content";
import { BLOCK_DEFAULTS } from "@/lib/blockDefaults";
import { saveBlocks } from "../../_actions/cms";
import { PageHeader, Card, SaveButton, Toast, fieldClass } from "@/components/admin/ui";

export const metadata: Metadata = { title: "Тексты страниц" };

type SP = Promise<{ page?: string; saved?: string }>;

export default async function ContentPage({ searchParams }: { searchParams: SP }) {
  const { page: pageParam, saved } = await searchParams;
  const pageKeys = Object.keys(BLOCK_DEFAULTS);
  const page = pageParam && pageKeys.includes(pageParam) ? pageParam : "home";

  // Ensure default blocks exist, then load them with their labels.
  await getBlocks(page, BLOCK_DEFAULTS[page].blocks);
  const blocks = await prisma.contentBlock.findMany({
    where: { page },
    orderBy: { key: "asc" },
  });

  // Preserve label/order from the registry.
  const order = Object.keys(BLOCK_DEFAULTS[page].blocks);
  blocks.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));

  return (
    <div>
      <PageHeader title="Тексты страниц" description="Редактируйте заголовки и тексты на страницах сайта." />
      <Toast show={!!saved}>Тексты сохранены.</Toast>

      <div className="mb-6 flex flex-wrap gap-2">
        {pageKeys.map((k) => (
          <Link
            key={k}
            href={`/admin/content?page=${k}`}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${
              k === page ? "bg-sage text-white" : "border border-cream-deep bg-white text-ink-soft hover:bg-cream-deep/60"
            }`}
          >
            {BLOCK_DEFAULTS[k].title}
          </Link>
        ))}
      </div>

      <form action={saveBlocks}>
        <input type="hidden" name="page" value={page} />
        <Card>
          <div className="space-y-5">
            {blocks.map((b) => {
              const def = BLOCK_DEFAULTS[page].blocks[b.key];
              const isLong = b.value.length > 90 || b.key === "body" || b.key.includes("text") || b.key.includes("subtitle") || b.key.includes("description");
              return (
                <label key={b.id} className="block">
                  <span className="mb-1.5 block text-sm font-medium text-ink">{def?.label || b.key}</span>
                  <input type="hidden" name="blockId" value={b.id} />
                  {isLong ? (
                    <textarea name={`value_${b.id}`} defaultValue={b.value} rows={3} className={fieldClass} />
                  ) : (
                    <input name={`value_${b.id}`} defaultValue={b.value} className={fieldClass} />
                  )}
                </label>
              );
            })}
          </div>
          <div className="mt-6">
            <SaveButton />
          </div>
        </Card>
      </form>
    </div>
  );
}
