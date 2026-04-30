#!/usr/bin/env node
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

const requiredFiles = [
  "AGENTS.md",
  "ARCHITECTURE.md",
  "docs/README.md",
  "docs/agent-harness.md",
  "docs/exec-plans/README.md",
  "docs/exec-plans/tech-debt-tracker.md",
  "docs/file-lifecycle-contract.md",
  "docs/release-governance.md",
];

const markdownFiles = [
  "AGENTS.md",
  "ARCHITECTURE.md",
  "README.md",
  "CONTRIBUTING.md",
  "docs/README.md",
  "docs/agent-harness.md",
  "docs/exec-plans/README.md",
  "docs/exec-plans/tech-debt-tracker.md",
];

let failures = 0;

function fail(message) {
  failures += 1;
  console.error(`[agent-docs] ${message}`);
}

for (const rel of requiredFiles) {
  if (!existsSync(path.join(repoRoot, rel))) {
    fail(`Missing required agent documentation file: ${rel}`);
  }
}

const markdownLinkPattern = /!?\[[^\]]*]\(([^)]+)\)/g;

for (const rel of markdownFiles) {
  const abs = path.join(repoRoot, rel);
  if (!existsSync(abs)) {
    continue;
  }
  const dir = path.dirname(abs);
  const text = readFileSync(abs, "utf8");
  for (const match of text.matchAll(markdownLinkPattern)) {
    const target = match[1].trim();
    if (
      !target ||
      target.startsWith("#") ||
      /^[a-z][a-z0-9+.-]*:/i.test(target) ||
      target.startsWith("mailto:")
    ) {
      continue;
    }
    const withoutAnchor = target.split("#")[0];
    if (!withoutAnchor) {
      continue;
    }
    const targetPath = path.resolve(dir, decodeURIComponent(withoutAnchor));
    if (!targetPath.startsWith(repoRoot) || !existsSync(targetPath)) {
      fail(`${rel} links to missing local target: ${target}`);
    }
  }
}

if (failures > 0) {
  console.error(`[agent-docs] Failed with ${failures} documentation issue(s).`);
  process.exit(1);
}

console.error("[agent-docs] Agent documentation map is valid.");
