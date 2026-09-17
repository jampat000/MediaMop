#!/usr/bin/env node
// NuGet vulnerability gate for the .NET server (and any other solution or project passed in).
//
//   node scripts/check-dotnet-vulnerabilities.mjs apps/server/Weir.slnx [more projects...]
//
// Runs `dotnet list <target> package --vulnerable --include-transitive --format json` against the
// NuGet advisory database and fails when any direct or transitive package has a High or Critical
// advisory. Lower severities are printed but do not fail, matching `npm audit --audit-level=high`
// for the web app. The target must already be restored (a build does that).

import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FAILING = new Set(["high", "critical"]);
const targets = process.argv.slice(2);
if (targets.length === 0) {
  console.error("usage: node scripts/check-dotnet-vulnerabilities.mjs <solution-or-project> [...]");
  process.exit(2);
}

let failing = 0;
let reported = 0;
for (const target of targets) {
  let raw;
  try {
    raw = execFileSync(
      "dotnet",
      ["list", target, "package", "--vulnerable", "--include-transitive", "--format", "json"],
      { cwd: REPO, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
    );
  } catch (err) {
    console.error(`[dotnet-vulnerabilities] dotnet list failed for ${target}:`);
    console.error(err.stdout ?? "");
    console.error(err.stderr ?? err.message);
    process.exit(2);
  }
  const report = JSON.parse(raw);
  for (const problem of report.problems ?? []) {
    // A source that could not be reached means the scan did not happen; do not pass silently.
    console.error(`[dotnet-vulnerabilities] ${target}: ${problem.level ?? "problem"}: ${problem.text}`);
    if ((problem.level ?? "").toLowerCase() === "error") failing += 1;
  }
  for (const project of report.projects ?? []) {
    for (const framework of project.frameworks ?? []) {
      const packages = [...(framework.topLevelPackages ?? []), ...(framework.transitivePackages ?? [])];
      for (const pkg of packages) {
        for (const vulnerability of pkg.vulnerabilities ?? []) {
          const severity = String(vulnerability.severity ?? "unknown").toLowerCase();
          const line = `${path.relative(REPO, project.path)} (${framework.framework}): ${pkg.id} ${pkg.resolvedVersion} - ${severity} - ${vulnerability.advisoryurl}`;
          reported += 1;
          if (FAILING.has(severity)) {
            failing += 1;
            console.error(`[dotnet-vulnerabilities] FAIL ${line}`);
          } else {
            console.log(`[dotnet-vulnerabilities] note ${line}`);
          }
        }
      }
    }
  }
}

if (failing) {
  console.error(`[dotnet-vulnerabilities] ${failing} High/Critical advisory finding(s) or scan error(s).`);
  process.exit(1);
}
console.log(`[dotnet-vulnerabilities] No High or Critical advisories (${reported} lower-severity finding(s)).`);
