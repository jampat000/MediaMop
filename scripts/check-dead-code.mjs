#!/usr/bin/env node
// Dead-code guard for Weir.
//
// Three refactors landed their behaviour change and left the old code in the tree
// (#328). Nothing caught it, because nothing was looking. This looks.
//
//   web    — `ts-prune` for exports nothing imports (this script).
//   server — the .NET build itself: apps/server/.editorconfig raises IDE0051 (unused private
//            members) and IDE0052 (private members never read) to warnings, and the build treats
//            warnings as errors, alongside the recommended CA analyzers (e.g. CA1812, internal
//            classes nothing instantiates). `dotnet build apps/server/Weir.slnx -warnaserror` is
//            that half of the guard, so it is not repeated here.
//
// The web half compares against `scripts/dead-code-allowlist.json` and fails only on entries
// that are *not* listed. The allowlist is the deliberate part: something kept on
// purpose gets a line and a reason, and anything else is a build failure. Keeping a
// silent baseline instead would just be the same accumulation with extra steps.

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(REPO, "apps", "web");
const ALLOWLIST = path.join(REPO, "scripts", "dead-code-allowlist.json");

const allow = JSON.parse(readFileSync(ALLOWLIST, "utf8"));
const allowedWeb = new Set(Object.keys(allow.webExports ?? {}));

function webUnusedExports() {
  // ts-prune's own JS entry, run with this node. Avoids `npx` (a shell on Windows,
  // which node refuses to spawn without one) and the .bin/*.cmd shim entirely.
  const entry = path.join(WEB, "node_modules", "ts-prune", "lib", "index.js");
  if (!existsSync(entry)) {
    return { skipped: "apps/web/node_modules is missing (run npm ci)" };
  }
  let raw = "";
  try {
    raw = execFileSync(process.execPath, [entry, "-p", "tsconfig.json"], { cwd: WEB, encoding: "utf8" });
  } catch (err) {
    // ts-prune exits non-zero when it reports findings; the findings are on stdout.
    raw = err.stdout ?? "";
    if (!raw) throw err;
  }
  return {
    findings: raw
      .split(/\r?\n/)
      .filter((line) => line.trim() && !line.includes("(used in module)"))
      // Generated from the OpenAPI schema; unused members are the schema's business.
      .filter((line) => !line.includes("openapi-types"))
      .map((line) => line.trim().replace(/\\/g, "/").replace(/^\/?src/, "src")),
  };
}

function report(label, findings, allowed, reasons) {
  const unexpected = findings.filter((f) => !allowed.has(f));
  const stale = [...allowed].filter((a) => !findings.includes(a));
  if (unexpected.length) {
    console.error(`[dead-code] ${label}: ${unexpected.length} unreferenced item(s) not on the allowlist:`);
    for (const f of unexpected) console.error(`  ${f}`);
    console.error(`  Remove them, wire them to a real consumer, or add them to scripts/dead-code-allowlist.json`);
    console.error(`  with a reason if they are deliberately kept.`);
  }
  if (stale.length) {
    console.error(`[dead-code] ${label}: allowlist entries that are no longer dead (remove them):`);
    for (const f of stale) console.error(`  ${f}  — ${reasons[f]}`);
  }
  return unexpected.length + stale.length;
}

let failures = 0;

const web = webUnusedExports();
if (web.skipped) {
  console.log(`[dead-code] web skipped: ${web.skipped}`);
} else {
  failures += report("web exports", web.findings, allowedWeb, allow.webExports);
  console.log(`[dead-code] web exports: ${web.findings.length} unreferenced, ${allowedWeb.size} allowlisted`);
}

if (failures) {
  process.exit(1);
}
console.log("[dead-code] No unexpected dead code.");
