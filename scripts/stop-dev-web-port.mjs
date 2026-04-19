#!/usr/bin/env node
/**
 * Stops processes **listening** on the dev **Vite** port from ``scripts/dev-ports.json``
 * (override with ``MEDIAMOP_DEV_WEB_PORT``).
 *
 * Use when ``npm run dev`` fails with **Port 8782 is already in use** (leftover Node/Vite).
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { platform } from "node:os";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.join(__dirname, "..");
const devPortsPath = path.join(repoRoot, "scripts", "dev-ports.json");

function readWebPort() {
  const forced = (process.env.MEDIAMOP_DEV_WEB_PORT || "").trim();
  if (forced) {
    return Number(forced);
  }
  const raw = JSON.parse(readFileSync(devPortsPath, "utf8"));
  return Number(raw.development.webPort);
}

function listeningPidsWindowsNetTcp(port) {
  const p = Number(port);
  if (!Number.isFinite(p) || p < 1 || p > 65535) {
    return new Set();
  }
  const ps = [
    "Get-NetTCPConnection",
    "-LocalPort",
    String(p),
    "-State",
    "Listen",
    "-ErrorAction",
    "SilentlyContinue",
    "|",
    "Select-Object",
    "-ExpandProperty",
    "OwningProcess",
    "-Unique",
  ].join(" ");
  try {
    const out = execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", ps], {
      encoding: "utf8",
      windowsHide: true,
    });
    return new Set(
      out
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter((s) => /^\d+$/.test(s)),
    );
  } catch {
    return new Set();
  }
}

function listeningPidsWindowsNetstat(port) {
  const out = execFileSync("netstat", ["-ano"], { encoding: "utf8" });
  const pids = new Set();
  const suffix = `:${port}`;
  for (const line of out.split("\n")) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 5 || parts[0] !== "TCP") {
      continue;
    }
    const local = parts[1];
    if (!local.endsWith(suffix) && !local.endsWith(`]:${port}`)) {
      continue;
    }
    const stateIdx = parts.indexOf("LISTENING");
    if (stateIdx === -1) {
      continue;
    }
    const pid = parts[stateIdx + 1];
    if (pid && /^\d+$/.test(pid)) {
      pids.add(pid);
    }
  }
  return pids;
}

function listeningPidsUnix(port) {
  try {
    const out = execFileSync("lsof", ["-i", `TCP:${port}`, "-sTCP:LISTEN", "-t"], {
      encoding: "utf8",
    });
    return new Set(
      out
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    );
  } catch {
    return new Set();
  }
}

function stopListenersWindowsPowerShell(port) {
  const p = Number(port);
  const script = `
$ErrorActionPreference = 'SilentlyContinue'
$pids = @(Get-NetTCPConnection -LocalPort ${p} -State Listen | Select-Object -ExpandProperty OwningProcess -Unique)
$n = 0
foreach ($id in $pids) {
  if (-not $id) { continue }
  try {
    Stop-Process -Id $id -Force -ErrorAction Stop
    $n = $n + 1
  } catch { }
}
Write-Output $n
exit 0
`.trim();
  try {
    const out = execFileSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
      encoding: "utf8",
      windowsHide: true,
    });
    const n = Number.parseInt(String(out).trim(), 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch {
    return 0;
  }
}

function killPidWindows(pid) {
  try {
    execFileSync("taskkill", ["/F", "/PID", pid], { stdio: "inherit" });
    return true;
  } catch {
    return false;
  }
}

function killPidUnix(pid) {
  try {
    process.kill(Number(pid), "SIGTERM");
    return true;
  } catch {
    try {
      execFileSync("kill", ["-9", pid], { stdio: "inherit" });
      return true;
    } catch {
      return false;
    }
  }
}

const port = readWebPort();

if (platform() === "win32") {
  const netTcp = listeningPidsWindowsNetTcp(port);
  if (netTcp.size > 0) {
    console.error(
      `[stop-dev-web-port] Stopping listener(s) on port ${port} via PowerShell (PIDs: ${[...netTcp].join(", ")}).`,
    );
    let stopped = stopListenersWindowsPowerShell(port);
    if (stopped === 0) {
      console.error("[stop-dev-web-port] PowerShell Stop-Process had no effect — trying taskkill…");
      for (const pid of netTcp) {
        if (killPidWindows(pid)) {
          stopped += 1;
        }
      }
    }
    if (stopped > 0) {
      console.error(`[stop-dev-web-port] Stopped ${stopped} process(es).`);
    } else {
      console.error(
        "[stop-dev-web-port] Could not stop listener(s) — close the stray Vite terminal or run from an elevated PowerShell.",
      );
    }
    process.exit(0);
  }
}

const pids = platform() === "win32" ? listeningPidsWindowsNetstat(port) : listeningPidsUnix(port);

if (pids.size === 0) {
  console.error(`[stop-dev-web-port] No LISTENING process on TCP port ${port}.`);
  process.exit(0);
}

console.error(`[stop-dev-web-port] Stopping ${pids.size} process(es) on port ${port}: ${[...pids].join(", ")}`);

let ok = 0;
for (const pid of pids) {
  const killed = platform() === "win32" ? killPidWindows(pid) : killPidUnix(pid);
  if (killed) {
    ok += 1;
  }
}

if (ok === 0 && pids.size > 0) {
  console.error(
    "[stop-dev-web-port] No processes were stopped (PIDs from netstat were already gone or taskkill failed).",
  );
} else {
  console.error(`[stop-dev-web-port] Done (${ok}/${pids.size}).`);
}
process.exit(0);
