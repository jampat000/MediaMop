import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const exceptions = JSON.parse(readFileSync(path.join(siteRoot, "dependency-audit-exceptions.json"), "utf8"));
const allowed = new Map(exceptions.exceptions.map((item) => [item.advisory, item]));
const npm = process.platform === "win32" ? process.env.ComSpec : "npm";
const npmArgs = process.platform === "win32" ? ["/d", "/s", "/c", "npm audit --json"] : ["audit", "--json"];
const result = spawnSync(npm, npmArgs, {
  cwd: siteRoot,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "pipe"],
});

let report;
try {
  report = JSON.parse(result.stdout || "{}");
} catch {
  console.error(result.stderr || result.stdout || "[docs-audit] npm audit did not return JSON.");
  process.exit(result.status || 1);
}

const vulnerabilities = report.vulnerabilities ?? {};
const seenAdvisories = new Set();
const unexpected = new Set();
const expired = new Set();
const today = new Date().toISOString().slice(0, 10);

function inspect(name, entry, trail = new Set()) {
  if (!entry || trail.has(name)) return true;
  const nextTrail = new Set(trail).add(name);
  let safe = true;
  for (const via of entry.via ?? []) {
    if (typeof via === "string") {
      if (!inspect(via, vulnerabilities[via], nextTrail)) safe = false;
      continue;
    }
    const advisory = String(via.url || "").split("/").at(-1);
    if (!advisory) {
      safe = false;
      continue;
    }
    seenAdvisories.add(advisory);
    const exception = allowed.get(advisory);
    if (!exception) {
      unexpected.add(`${name}: ${advisory}`);
    } else if (exception.expires < today) {
      expired.add(advisory);
    }
  }
  return safe && !unexpected.has(name);
}

for (const [name, entry] of Object.entries(vulnerabilities)) inspect(name, entry);
for (const advisory of allowed.keys()) {
  if (seenAdvisories.has(advisory) && !allowed.get(advisory).mitigation) unexpected.add(`Missing mitigation metadata: ${advisory}`);
}

if (unexpected.size || expired.size) {
  console.error("[docs-audit] Dependency audit has an unapproved or expired finding:");
  for (const item of unexpected) console.error(`- ${item}`);
  for (const item of expired) console.error(`- Expired exception: ${item}`);
  process.exit(1);
}

if (result.status !== 0 && seenAdvisories.size === 0) {
  console.error(result.stderr || "[docs-audit] npm audit failed without a documented advisory.");
  process.exit(result.status || 1);
}

console.log(`[docs-audit] ${seenAdvisories.size} advisory path(s) are covered by current exception metadata.`);
