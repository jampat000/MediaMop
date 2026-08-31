import { readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptDir, "..");
const distRoot = path.join(webRoot, "dist");

function filesUnder(root) {
  if (!statSync(root, { throwIfNoEntry: false })) return [];
  const result = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const absolute = path.join(root, entry.name);
    if (entry.isDirectory()) result.push(...filesUnder(absolute));
    else result.push(absolute);
  }
  return result;
}

const files = filesUnder(distRoot);
const failures = [];
const maxBytes = (name) => Math.round(name * 1024);

for (const file of files) {
  const relative = path.relative(distRoot, file).replaceAll("\\", "/");
  const size = statSync(file).size;
  if (relative.endsWith(".map") && process.env.MEDIAMOP_BUILD_SOURCEMAPS !== "true") {
    failures.push(`${relative} is a source map; set MEDIAMOP_BUILD_SOURCEMAPS=true only for a diagnostics build`);
  }
  if (/logo-sidebar/i.test(relative) && size > maxBytes(20)) {
    failures.push(`${relative} is ${size} bytes; the sidebar logo budget is 20 KiB`);
  }
  if (/\.css$/i.test(relative) && size > maxBytes(180)) {
    failures.push(`${relative} is ${size} bytes; the stylesheet budget is 180 KiB`);
  }
  if (/\.js$/i.test(relative) && size > maxBytes(500)) {
    failures.push(`${relative} is ${size} bytes; the JavaScript chunk budget is 500 KiB`);
  }
}

if (failures.length) {
  console.error("[bundle-budget] Failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`[bundle-budget] ${files.length} files are within artifact and source-map policy.`);
