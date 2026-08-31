#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workflowFiles = execFileSync("git", ["ls-files", ".github/workflows"], {
  cwd: root,
  encoding: "utf8",
}).split(/\r?\n/).filter(Boolean);
const failures = [];

for (const relative of workflowFiles) {
  const text = readFileSync(path.resolve(root, relative), "utf8");
  for (const match of text.matchAll(/\buses:\s*([^\s#]+)/g)) {
    const reference = match[1];
    const at = reference.lastIndexOf("@");
    if (at < 1 || !/^[0-9a-f]{40}$/i.test(reference.slice(at + 1))) {
      failures.push(`${relative}: ${reference}`);
    }
  }
}

if (failures.length) {
  console.error("GitHub Actions must be pinned to a full commit SHA:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}
console.log("All GitHub Actions are pinned to full commit SHAs.");
