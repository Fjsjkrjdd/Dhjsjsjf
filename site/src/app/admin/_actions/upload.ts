"use server";

import { writeFile, mkdir } from "fs/promises";
import path from "path";
import { randomUUID } from "crypto";
import { getSession } from "@/lib/auth";

const ALLOWED = ["image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"];

/**
 * Saves an uploaded image into /public/uploads and returns its public path.
 * Returns "" when no file was provided.
 */
export async function uploadImage(formData: FormData, field = "file"): Promise<string> {
  const session = await getSession();
  if (!session) throw new Error("Unauthorized");

  const file = formData.get(field);
  if (!file || !(file instanceof File) || file.size === 0) return "";

  if (!ALLOWED.includes(file.type)) {
    throw new Error("Недопустимый формат файла");
  }

  const ext = file.name.split(".").pop()?.toLowerCase() || "jpg";
  const name = `${randomUUID()}.${ext}`;
  const dir = path.join(process.cwd(), "public", "uploads");
  await mkdir(dir, { recursive: true });
  const bytes = Buffer.from(await file.arrayBuffer());
  await writeFile(path.join(dir, name), bytes);
  return `/uploads/${name}`;
}
