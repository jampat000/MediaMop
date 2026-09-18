#!/usr/bin/env node
/**
 * Stops **this worktree's** dev API process — the one `apps/web/scripts/run-api-dev.mjs`
 * spawned and recorded in `.dev-api.pid` at the repo root — and nothing else.
 *
 * This used to stop whatever process was *listening on the dev API port*, full stop. That is
 * unsafe: the dev API port and an installed Weir's port can be the same number (they both
 * default to the same value — see `scripts/dev-ports.json` and `docs/ports.md`), so on any
 * machine that also has Weir installed, this command would silently kill the installed
 * instance instead of (or as well as) the dev one. The installer had the equivalent bug —
 * killing every process merely *named* Weir — and was fixed by matching on the install's own
 * folder (`apps/tray/Weir.Tray/InstallProcesses.cs`, `InstallProcesses.IsInside`). This script
 * applies the same principle: identify the exact process before touching it, never infer it
 * from what happens to hold a port.
 *
 * Use when an old dev API process from *this* worktree is still bound (a current route
 * returns 404) or the port is stuck. Then run `npm run dev` from `apps/web` again.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { platform } from "node:os";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.join(__dirname, "..");
const pidFilePath = path.join(repoRoot, ".dev-api.pid");

function removePidFile() {
  try {
    rmSync(pidFilePath, { force: true });
  } catch {
    /* ignore — best-effort cleanup */
  }
}

function readRecordedProcess() {
  if (!existsSync(pidFilePath)) {
    return null;
  }
  try {
    const raw = JSON.parse(readFileSync(pidFilePath, "utf8"));
    const pid = Number(raw?.pid);
    const serverProject = String(raw?.serverProject || "");
    if (!Number.isInteger(pid) || pid <= 0 || !serverProject) {
      return null;
    }
    return { pid, serverProject };
  } catch {
    return null;
  }
}

/**
 * Windows: `Get-CimInstance Win32_Process` exposes the exact command line, which is what lets
 * us tell "this PID is dotnet running *our* Weir.Host project" apart from "this PID happens to
 * exist and answers to the same number" (PIDs are recycled by the OS soon after a process
 * exits, so the bare fact that *some* process has this PID proves nothing on its own).
 * @returns {{ ok: boolean, commandLine: string } | null} null when the PID is not running.
 */
function describeWindowsProcess(pid) {
  const ps = [
    "$p = Get-CimInstance Win32_Process -Filter \"ProcessId=${pid}\" -ErrorAction SilentlyContinue;",
    "if ($p) { Write-Output $p.CommandLine } else { Write-Output '' }",
  ].join(" ");
  try {
    const out = execFileSync(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", ps.replace("${pid}", String(pid))],
      { encoding: "utf8", windowsHide: true },
    );
    const commandLine = out.trim();
    return commandLine ? { commandLine } : null;
  } catch {
    return null;
  }
}

/** @returns {{ commandLine: string } | null} null when the PID is not running. */
function describeUnixProcess(pid) {
  try {
    const out = execFileSync("ps", ["-p", String(pid), "-o", "command="], {
      encoding: "utf8",
    });
    const commandLine = out.trim();
    return commandLine ? { commandLine } : null;
  } catch {
    return null;
  }
}

function stopProcessTreeWindows(pid) {
  try {
    execFileSync("taskkill", ["/T", "/F", "/PID", String(pid)], { stdio: "inherit" });
    return true;
  } catch {
    return false;
  }
}

/** Kills the recorded PID's whole process group (it was spawned detached; see run-api-dev.mjs). */
function stopProcessTreeUnix(pid) {
  try {
    process.kill(-pid, "SIGTERM");
    return true;
  } catch {
    try {
      process.kill(pid, "SIGTERM");
      return true;
    } catch {
      return false;
    }
  }
}

const recorded = readRecordedProcess();

if (!recorded) {
  console.error(
    "[stop-dev-api-port] No recorded dev API process for this worktree (.dev-api.pid missing " +
      "or unreadable) — nothing to stop. This only stops a process `npm run dev` itself started; " +
      "it never scans the port for arbitrary listeners (that could be an installed Weir).",
  );
  process.exit(0);
}

const isWindows = platform() === "win32";
const description = isWindows
  ? describeWindowsProcess(recorded.pid)
  : describeUnixProcess(recorded.pid);

if (!description) {
  console.error(
    `[stop-dev-api-port] Recorded PID ${recorded.pid} is not running (already stopped, or the ` +
      "machine restarted) — clearing the stale record.",
  );
  removePidFile();
  process.exit(0);
}

const identifies = description.commandLine.includes(recorded.serverProject);

if (!identifies) {
  console.error(
    `[stop-dev-api-port] PID ${recorded.pid} is running but is not this worktree's dev API — ` +
      `its command line does not reference ${recorded.serverProject}. The OS likely reused the ` +
      "PID for an unrelated process after the dev API exited. Leaving it alone: not knowing is " +
      "not permission. Clearing the stale record.",
  );
  removePidFile();
  process.exit(0);
}

console.error(
  `[stop-dev-api-port] Stopping this worktree's dev API (PID ${recorded.pid}, ${recorded.serverProject}).`,
);
const stopped = isWindows
  ? stopProcessTreeWindows(recorded.pid)
  : stopProcessTreeUnix(recorded.pid);

if (stopped) {
  console.error("[stop-dev-api-port] Stopped.");
} else {
  console.error(
    `[stop-dev-api-port] Could not stop PID ${recorded.pid} — close the terminal running the ` +
      "API, or run this from an elevated shell.",
  );
}
removePidFile();
process.exit(0);
