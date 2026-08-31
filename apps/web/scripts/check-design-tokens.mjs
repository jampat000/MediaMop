import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptDir, "..");
const sourceRoot = path.join(webRoot, "src");
const tokenPath = path.join(sourceRoot, "styles", "mediamop-tokens.css");
const allowedExtensions = new Set([".css", ".ts", ".tsx"]);
const requiredTokens = [
  "mm-text1",
  "mm-surface1",
  "mm-surface2",
  "mm-status-healthy-text",
  "mm-status-warning-text",
  "mm-status-failed-text",
  "mm-status-info-text",
];

async function collectSourceFiles(directory) {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectSourceFiles(fullPath)));
    } else if (allowedExtensions.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
}

const tokenSource = await fs.readFile(tokenPath, "utf8");
const definitions = new Set(
  [...tokenSource.matchAll(/--(mm-[A-Za-z0-9_-]+)\s*:/g)].map(
    ([, token]) => token,
  ),
);
const missingRequired = requiredTokens.filter((token) => !definitions.has(token));
const references = new Map();

for (const filePath of await collectSourceFiles(sourceRoot)) {
  const source = await fs.readFile(filePath, "utf8");
  for (const match of source.matchAll(/var\(\s*--(mm-[A-Za-z0-9_-]+)/g)) {
    const token = match[1];
    if (!definitions.has(token) && !references.has(token)) {
      references.set(token, path.relative(webRoot, filePath));
    }
  }
}

if (missingRequired.length || references.size) {
  if (missingRequired.length) {
    console.error(`Missing required semantic tokens: ${missingRequired.join(", ")}`);
  }
  for (const [token, file] of references) {
    console.error(`Undefined semantic token --${token} referenced by ${file}`);
  }
  process.exit(1);
}

console.log(
  `Design token check passed (${definitions.size} definitions; semantic references resolved).`,
);
