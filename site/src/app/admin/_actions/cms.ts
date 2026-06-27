"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { getSession } from "@/lib/auth";
import { uploadImage } from "./upload";

async function requireAuth() {
  const session = await getSession();
  if (!session) redirect("/admin/login");
  return session;
}

function str(fd: FormData, key: string, fallback = ""): string {
  const v = fd.get(key);
  return v === null ? fallback : String(v).trim();
}
function int(fd: FormData, key: string, fallback = 0): number {
  const n = parseInt(String(fd.get(key) ?? ""), 10);
  return Number.isNaN(n) ? fallback : n;
}
function bool(fd: FormData, key: string): boolean {
  const v = fd.get(key);
  return v === "on" || v === "true" || v === "1";
}
function slugify(s: string): string {
  const map: Record<string, string> = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z",
    и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r",
    с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "c", ч: "ch", ш: "sh", щ: "sch",
    ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
  };
  return s
    .toLowerCase()
    .split("")
    .map((c) => map[c] ?? c)
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || `item-${Date.now()}`;
}

function revalidateAll() {
  revalidatePath("/", "layout");
}

/* ----------------------------- Settings ------------------------------- */
export async function saveSettings(fd: FormData) {
  await requireAuth();
  const heroUpload = await uploadImage(fd, "heroPhotoFile");
  const aboutUpload = await uploadImage(fd, "aboutPhotoFile");

  const data: Record<string, unknown> = {
    siteName: str(fd, "siteName"),
    ownerName: str(fd, "ownerName"),
    profession: str(fd, "profession"),
    tagline: str(fd, "tagline"),
    logoText: str(fd, "logoText"),
    phone: str(fd, "phone"),
    email: str(fd, "email"),
    address: str(fd, "address"),
    city: str(fd, "city"),
    workingHours: str(fd, "workingHours"),
    mapEmbed: str(fd, "mapEmbed"),
    vk: str(fd, "vk"),
    telegram: str(fd, "telegram"),
    whatsapp: str(fd, "whatsapp"),
    instagram: str(fd, "instagram"),
    youtube: str(fd, "youtube"),
    yandexMaps: str(fd, "yandexMaps"),
    metaTitle: str(fd, "metaTitle"),
    metaDescription: str(fd, "metaDescription"),
    paymentsEnabled: bool(fd, "paymentsEnabled"),
    paymentProvider: str(fd, "paymentProvider", "yookassa"),
    yooKassaShopId: str(fd, "yooKassaShopId"),
    fiscalEnabled: bool(fd, "fiscalEnabled"),
    taxSystemCode: int(fd, "taxSystemCode", 2),
    vatCode: int(fd, "vatCode", 1),
    paymentSubject: str(fd, "paymentSubject", "service"),
    paymentMode: str(fd, "paymentMode", "full_payment"),
  };
  // Only overwrite secret key if a new value was provided.
  const secret = str(fd, "yooKassaSecretKey");
  if (secret) data.yooKassaSecretKey = secret;
  if (heroUpload) data.heroPhoto = heroUpload;
  else if (str(fd, "heroPhoto")) data.heroPhoto = str(fd, "heroPhoto");
  if (aboutUpload) data.aboutPhoto = aboutUpload;
  else if (str(fd, "aboutPhoto")) data.aboutPhoto = str(fd, "aboutPhoto");

  await prisma.siteSettings.upsert({
    where: { id: 1 },
    update: data,
    create: { id: 1, ...data },
  });
  revalidateAll();
  redirect("/admin/settings?saved=1");
}

/* -------------------------- Content blocks ----------------------------- */
export async function saveBlocks(fd: FormData) {
  await requireAuth();
  const page = str(fd, "page");
  const ids = fd.getAll("blockId").map(String);
  await prisma.$transaction(
    ids.map((id) =>
      prisma.contentBlock.update({
        where: { id },
        data: { value: str(fd, `value_${id}`) },
      }),
    ),
  );
  revalidateAll();
  redirect(`/admin/content?page=${page}&saved=1`);
}

/* ------------------------------ Services ------------------------------- */
export async function saveService(fd: FormData) {
  await requireAuth();
  const id = str(fd, "id");
  const image = (await uploadImage(fd, "imageFile")) || str(fd, "image");
  const title = str(fd, "title");
  const data = {
    title,
    slug: str(fd, "slug") || slugify(title),
    shortDescription: str(fd, "shortDescription"),
    description: str(fd, "description"),
    price: int(fd, "price"),
    oldPrice: str(fd, "oldPrice") ? int(fd, "oldPrice") : null,
    priceSuffix: str(fd, "priceSuffix"),
    duration: str(fd, "duration"),
    icon: str(fd, "icon", "heart"),
    image,
    isActive: bool(fd, "isActive"),
    isBookable: bool(fd, "isBookable"),
    order: int(fd, "order"),
  };
  if (id) await prisma.service.update({ where: { id }, data });
  else await prisma.service.create({ data });
  revalidateAll();
  redirect("/admin/services");
}
export async function deleteService(fd: FormData) {
  await requireAuth();
  await prisma.service.delete({ where: { id: str(fd, "id") } });
  revalidateAll();
  redirect("/admin/services");
}

/* ------------------------------ Diplomas ------------------------------- */
export async function saveDiploma(fd: FormData) {
  await requireAuth();
  const id = str(fd, "id");
  const image = (await uploadImage(fd, "imageFile")) || str(fd, "image");
  if (!image) redirect("/admin/diplomas?error=image");
  const data = {
    title: str(fd, "title", "Диплом"),
    description: str(fd, "description"),
    image,
    order: int(fd, "order"),
    isPublished: bool(fd, "isPublished"),
  };
  if (id) await prisma.diploma.update({ where: { id }, data });
  else await prisma.diploma.create({ data });
  revalidateAll();
  redirect("/admin/diplomas");
}
export async function deleteDiploma(fd: FormData) {
  await requireAuth();
  await prisma.diploma.delete({ where: { id: str(fd, "id") } });
  revalidateAll();
  redirect("/admin/diplomas");
}

/* ------------------------------- Reviews ------------------------------- */
export async function saveReview(fd: FormData) {
  await requireAuth();
  const id = str(fd, "id");
  const data = {
    author: str(fd, "author"),
    text: str(fd, "text"),
    rating: Math.min(5, Math.max(1, int(fd, "rating", 5))),
    source: str(fd, "source"),
    date: str(fd, "date"),
    isPublished: bool(fd, "isPublished"),
    order: int(fd, "order"),
  };
  if (id) await prisma.review.update({ where: { id }, data });
  else await prisma.review.create({ data });
  revalidateAll();
  redirect("/admin/reviews");
}
export async function deleteReview(fd: FormData) {
  await requireAuth();
  await prisma.review.delete({ where: { id: str(fd, "id") } });
  revalidateAll();
  redirect("/admin/reviews");
}

/* ------------------------------ Education ------------------------------ */
export async function saveEducation(fd: FormData) {
  await requireAuth();
  const id = str(fd, "id");
  const data = {
    title: str(fd, "title"),
    institution: str(fd, "institution"),
    year: str(fd, "year"),
    description: str(fd, "description"),
    order: int(fd, "order"),
  };
  if (id) await prisma.education.update({ where: { id }, data });
  else await prisma.education.create({ data });
  revalidateAll();
  redirect("/admin/education");
}
export async function deleteEducation(fd: FormData) {
  await requireAuth();
  await prisma.education.delete({ where: { id: str(fd, "id") } });
  revalidateAll();
  redirect("/admin/education");
}

/* ------------------------------ Articles ------------------------------- */
export async function saveArticle(fd: FormData) {
  await requireAuth();
  const id = str(fd, "id");
  const cover = (await uploadImage(fd, "coverFile")) || str(fd, "cover");
  const title = str(fd, "title");
  const data = {
    title,
    slug: str(fd, "slug") || slugify(title),
    excerpt: str(fd, "excerpt"),
    content: str(fd, "content"),
    cover,
    category: str(fd, "category"),
    isPublished: bool(fd, "isPublished"),
    metaTitle: str(fd, "metaTitle"),
    metaDescription: str(fd, "metaDescription"),
  };
  if (id) await prisma.article.update({ where: { id }, data });
  else await prisma.article.create({ data });
  revalidateAll();
  redirect("/admin/articles");
}
export async function deleteArticle(fd: FormData) {
  await requireAuth();
  await prisma.article.delete({ where: { id: str(fd, "id") } });
  revalidateAll();
  redirect("/admin/articles");
}

/* -------------------------------- Pages -------------------------------- */
export async function savePage(fd: FormData) {
  await requireAuth();
  const id = str(fd, "id");
  const title = str(fd, "title");
  const data = {
    title,
    slug: str(fd, "slug") || slugify(title),
    content: str(fd, "content"),
    metaTitle: str(fd, "metaTitle"),
    metaDescription: str(fd, "metaDescription"),
    isPublished: bool(fd, "isPublished"),
    showInMenu: bool(fd, "showInMenu"),
    order: int(fd, "order"),
  };
  if (id) await prisma.page.update({ where: { id }, data });
  else await prisma.page.create({ data });
  revalidateAll();
  redirect("/admin/pages");
}
export async function deletePage(fd: FormData) {
  await requireAuth();
  await prisma.page.delete({ where: { id: str(fd, "id") } });
  revalidateAll();
  redirect("/admin/pages");
}

/* -------------------------------- Orders ------------------------------- */
export async function updateOrderStatus(fd: FormData) {
  await requireAuth();
  await prisma.order.update({
    where: { id: str(fd, "id") },
    data: { status: str(fd, "status", "new") },
  });
  redirect("/admin/orders");
}
export async function deleteOrder(fd: FormData) {
  await requireAuth();
  await prisma.order.delete({ where: { id: str(fd, "id") } });
  redirect("/admin/orders");
}

/* ------------------------------ Account -------------------------------- */
export async function changePassword(fd: FormData) {
  const session = await requireAuth();
  const { hashPassword, verifyPassword } = await import("@/lib/auth");
  const current = str(fd, "current");
  const next = str(fd, "next");
  if (next.length < 6) redirect("/admin/account?error=short");
  const user = await prisma.user.findUnique({ where: { id: session.userId } });
  if (!user || !(await verifyPassword(current, user.passwordHash))) {
    redirect("/admin/account?error=current");
  }
  await prisma.user.update({
    where: { id: session.userId },
    data: { passwordHash: await hashPassword(next) },
  });
  redirect("/admin/account?saved=1");
}
