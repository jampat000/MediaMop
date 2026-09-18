#!/usr/bin/env node
// Dead-code guard for Weir.
//
// Three refactors landed their behaviour change and left the old code in the tree
// (#328). Nothing caught it, because nothing was looking. This looks.
//
//   web    — `ts-prune` for exports nothing imports (this script).
//   web    — phantom `mm-*` class names: markup styled by nothing (this script). The mirror
//            image of an unused export, and the same failure — code that reads as if it does
//            something and does not.
//   server — the .NET build itself: apps/server/.editorconfig raises IDE0051 (unused private
//            members) and IDE0052 (private members never read) to warnings, and the build treats
//            warnings as errors, alongside the recommended CA analyzers (e.g. CA1812, internal
//            classes nothing instantiates). `dotnet build apps/server/Weir.slnx -warnaserror` is
//            that half of the guard, so it is not repeated here.
//
// The ts-prune half compares against `scripts/dead-code-allowlist.json` and fails only on entries
// that are *not* listed. The allowlist is the deliberate part: something kept on
// purpose gets a line and a reason, and anything else is a build failure. Keeping a
// silent baseline instead would just be the same accumulation with extra steps.
//
// The phantom-class half has no allowlist on purpose — see the note above that check.

import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
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

// A class name on an element that no stylesheet has a rule for. #590 (the route error screen,
// eight invented names, the heading pushed below the fold) and #594 (the loading skeleton,
// placeholder divs collapsed to zero size) were both this, both shipped, and both sat in the
// tree for a long time because nothing was looking.
//
// The check is deliberately narrow, and each narrowing is what makes it trustworthy:
//
//   `mm-` only        — Weir's own namespace. Tailwind generates utilities prefixed by what they
//                       set (`bg-`, `text-`, `p-`), never a bare `mm-*`, so "absent from our CSS"
//                       means "styled by nothing" without the checker knowing any Tailwind at all.
//                       That is also why this needs no build: the stylesheet sources are the
//                       whole truth for this namespace.
//   plain literals    — `className="…"` only, never `{`…`}` or `{expr}`. Generated modifiers like
//                       `mm-activity-event-icon--${tone}` are the one honest source of noise: the
//                       base rule *is* the default tone, so `--info` correctly has no rule of its
//                       own. Excluding interpolation drops all of them structurally, instead of
//                       an allowlist that would need a line for every new tone.
//   line by line      — a `className` Prettier split across lines is missed. Accepted: it
//                       under-reports rather than crying wolf.
//
// Hence no allowlist. A finding here is a defect, not a judgement call: either the rule was never
// written or the name is a typo. Measured over the repo's history this has found 26 occurrences
// and zero false positives, so an escape hatch would only ever be used to wave a real bug through.
function phantomClassNames() {
  const SRC = path.join(WEB, "src");

  const files = [];
  (function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else files.push(p);
    }
  })(SRC);

  // Every mm-* name any stylesheet mentions, in a selector or anywhere else. Being generous here
  // is the right way to be wrong: it can only ever hide a finding, never invent one.
  const styled = new Set();
  for (const file of files.filter((f) => f.endsWith(".css"))) {
    const css = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, " ");
    for (const m of css.matchAll(/\.(mm-[\w-]+)/g)) styled.add(m[1]);
  }

  const findings = [];
  let literals = 0;
  for (const file of files.filter((f) => f.endsWith(".tsx"))) {
    // Tests render fixtures and assert on markup; a class name there is not a styling claim.
    if (file.endsWith(".test.tsx")) continue;
    const rel = path.relative(REPO, file).split(path.sep).join("/");
    readFileSync(file, "utf8")
      .split(/\r?\n/)
      .forEach((line, i) => {
        for (const m of line.matchAll(/className="([^"{}$`]*)"/g)) {
          for (const token of m[1].split(/\s+/)) {
            if (!/^mm-[\w-]+$/.test(token)) continue;
            literals += 1;
            if (styled.has(token)) continue;
            findings.push({ at: `${rel}:${i + 1}`, token });
          }
        }
      });
  }
  return { findings, literals, styled: styled.size };
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

const phantom = phantomClassNames();
if (phantom.findings.length) {
  console.error(
    `[dead-code] phantom classes: ${phantom.findings.length} mm-* class name(s) that no stylesheet styles:`,
  );
  for (const f of phantom.findings) console.error(`  ${f.at}  ${f.token}`);
  console.error(`  Each one is markup claiming a style that does not exist. Write the rule in`);
  console.error(`  apps/web/src/styles/, or drop the class name. There is no allowlist for these.`);
  failures += phantom.findings.length;
} else {
  console.log(
    `[dead-code] phantom classes: 0 of ${phantom.literals} literal mm-* use(s) unstyled, ` +
      `against ${phantom.styled} styled name(s).`,
  );
}

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
