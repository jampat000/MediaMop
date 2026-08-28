#!/usr/bin/env node
// Dead-code guard for MediaMop.
//
// Three refactors landed their behaviour change and left the old code in the tree
// (#328). Nothing caught it, because nothing was looking. This looks.
//
//   web     — `ts-prune` for exports nothing imports.
//   backend — modules under `src/mediamop` that nothing imports.
//
// Both compare against `scripts/dead-code-allowlist.json` and fail only on entries
// that are *not* listed. The allowlist is the deliberate part: something kept on
// purpose gets a line and a reason, and anything else is a build failure. Keeping a
// silent baseline instead would just be the same accumulation with extra steps.

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(REPO, "apps", "web");
const BACKEND_SRC = path.join(REPO, "apps", "backend", "src", "mediamop");
const BACKEND_TESTS = path.join(REPO, "apps", "backend", "tests");
// Migrations import product code (0001 seeds singleton rows), so they count as consumers.
const BACKEND_ALEMBIC = path.join(REPO, "apps", "backend", "alembic");
const ALLOWLIST = path.join(REPO, "scripts", "dead-code-allowlist.json");

const allow = JSON.parse(readFileSync(ALLOWLIST, "utf8"));
const allowedWeb = new Set(Object.keys(allow.webExports ?? {}));
const allowedBackend = new Set(Object.keys(allow.backendModules ?? {}));

function walk(dir, ext) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "__pycache__" || entry === "node_modules") continue;
      found.push(...walk(full, ext));
    } else if (entry.endsWith(ext)) {
      found.push(full);
    }
  }
  return found;
}

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

// `from mediamop.a.b import x`, `import mediamop.a.b`, and `from .sibling import x`
// resolved against the importing module's package.
function backendImportedModules() {
  const imported = new Set();
  const files = [...walk(BACKEND_SRC, ".py"), ...walk(BACKEND_TESTS, ".py"), ...walk(BACKEND_ALEMBIC, ".py")];
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(/^\s*(?:from|import)\s+(mediamop[\w.]*)/gm)) {
      const parts = m[1].split(".");
      // Record the module and every package above it, so importing a leaf keeps its
      // parents alive too.
      for (let i = parts.length; i > 1; i -= 1) imported.add(parts.slice(0, i).join("."));
    }
    // `from mediamop.a.b import c` may import the *module* c, not a symbol from b.
    // Both readings keep `mediamop.a.b.c` alive, so record every imported name —
    // over-counting here only ever means a module is treated as live, never as dead.
    for (const m of text.matchAll(/^\s*from\s+(mediamop[\w.]*)\s+import\s+(\([^)]*\)|[^\n]*)/gm)) {
      for (const name of m[2].replace(/[()]/g, " ").split(",")) {
        const symbol = name.trim().split(/\s+/)[0];
        if (/^\w+$/.test(symbol)) imported.add(`${m[1]}.${symbol}`);
      }
    }
    for (const m of text.matchAll(/^\s*from\s+(\.+)(\w[\w.]*)?\s+import\s+/gm)) {
      const rel = path.relative(BACKEND_SRC, path.dirname(file)).split(path.sep).filter(Boolean);
      const up = m[1].length - 1;
      const base = ["mediamop", ...rel.slice(0, rel.length - up)];
      if (m[2]) base.push(...m[2].split("."));
      imported.add(base.join("."));
    }
  }
  return imported;
}

function backendUnreferencedModules() {
  const imported = backendImportedModules();
  const findings = [];
  for (const file of walk(BACKEND_SRC, ".py")) {
    const rel = path.relative(BACKEND_SRC, file);
    if (path.basename(file) === "__init__.py") continue;
    const dotted = ["mediamop", ...rel.replace(/\.py$/, "").split(path.sep)].join(".");
    if (!imported.has(dotted)) {
      findings.push(`apps/backend/src/mediamop/${rel.replace(/\\/g, "/")}`);
    }
  }
  return findings;
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

const backend = backendUnreferencedModules();
failures += report("backend modules", backend, allowedBackend, allow.backendModules);
console.log(`[dead-code] backend modules: ${backend.length} unreferenced, ${allowedBackend.size} allowlisted`);

if (failures) {
  process.exit(1);
}
console.log("[dead-code] No unexpected dead code.");
