import { existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const roots = [path.join(siteRoot, "docs"), path.join(siteRoot, "static")];
const blocked = new Set([".icns", ".jxl", ".heic", ".heif"]);
const allowUnsafe = process.env.MEDIAMOP_ALLOW_UNSAFE_DOC_IMAGES === "true";

function walk(root) {
  if (!existsSync(root)) return [];
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const absolute = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...walk(absolute));
    else files.push(absolute);
  }
  return files;
}

const matches = roots.flatMap(walk).filter((file) => blocked.has(path.extname(file).toLowerCase()));
if (matches.length && !allowUnsafe) {
  console.error("[docs-images] Unsupported image formats found:");
  for (const file of matches) console.error(`- ${path.relative(siteRoot, file)}`);
  console.error("Convert these files to PNG, WebP, or SVG before the docs build. Set MEDIAMOP_ALLOW_UNSAFE_DOC_IMAGES=true only after the dependency exception is removed.");
  process.exit(1);
}

if (matches.length) console.warn(`[docs-images] Explicit override enabled for ${matches.length} unsupported image file(s).`);
else console.log("[docs-images] All documentation images use approved formats.");
