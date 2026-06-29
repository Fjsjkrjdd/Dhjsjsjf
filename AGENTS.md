# AGENTS.md

## Cursor Cloud specific instructions

### Repository layout
- The actual product is a psychologist website + CMS. Two implementations exist:
  - `site/` — **primary**: Next.js 16 (App Router) + TypeScript + Tailwind 4 + Prisma + SQLite. This is what you normally develop/run.
  - `php-site/` — a standalone PHP port of the same site for shared hosting. PHP is **not** installed in this environment by default; only set it up if a task targets `php-site/` (run locally via `php -S localhost:8000 router.php` from `php-site/`).
- Repo-root files like `PelengPC.zip`, `peleng_*.py`, and the `PELENG_REVERSE_*.md` notes are unrelated reverse-engineering artifacts — not part of the website and not needed to run it.

### Running the Next.js app (`site/`)
- All commands run from `site/`. Standard scripts are in `site/package.json` (`dev`, `build`, `start`, `lint`, `db:migrate`, `db:seed`, `db:reset`).
- **First-time DB setup is required** and is intentionally NOT part of the startup update script. The SQLite DB (`prisma/dev.db`) is gitignored, so on a fresh checkout (no existing DB) you must run once:
  - `cp .env.example .env` (if `.env` is missing)
  - `npm run db:migrate` then `npm run db:seed`
  - These are idempotent enough to re-run; use `npm run db:reset` to wipe and reseed.
- Start dev server: `npm run dev` (http://localhost:3000). Uses Turbopack.
- Admin panel: `/admin` (redirects to `/admin/login`). Seeded credentials come from `.env` (`ADMIN_EMAIL`/`ADMIN_PASSWORD`), default `admin@chernova-psy.ru` / `admin12345`.

### Non-obvious notes
- The public reviews page is at `/reviews` (not `/otzyvy`). Other public routes: `/about`, `/services`, `/articles`, `/contacts`, `/booking`.
- Content pages render dynamically (`force-dynamic`), so admin edits appear immediately without rebuild.
- YooKassa payment env vars (`YOOKASSA_SHOP_ID`/`YOOKASSA_SECRET_KEY`) are optional and can be left blank for local dev / non-payment flows.
- `prisma generate` runs automatically via the `postinstall` hook, so a plain `npm install` is enough to refresh the Prisma client.
