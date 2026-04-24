#!/usr/bin/env node
/**
 * Spawns the MediaMop API like `scripts/dev-backend.ps1` (cwd apps/backend, PYTHONPATH=src,
 * host/port from scripts/dev-ports.json). Used by `npm run dev` so Vite and uvicorn start together.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.join(__dirname, "..");
const repoRoot = path.resolve(webDir, "..", "..");
const backendDir = path.join(repoRoot, "apps", "backend");
const portsPath = path.join(repoRoot, "scripts", "dev-ports.json");
const defaultDevHome = path.join(repoRoot, ".local-dev-home");
const defaultDevSessionSecret = "dev-session-secret-32-chars-minimum!!";

function readPorts() {
  const raw = readFileSync(portsPath, "utf8");
  const j = JSON.parse(raw);
  return j.development;
}

/** Prefer backend venv, then system interpreters (matches dev-backend.ps1 intent). */
function resolvePythonCmd() {
  const winVenv = path.join(backendDir, ".venv", "Scripts", "python.exe");
  const unixVenv3 = path.join(backendDir, ".venv", "bin", "python3");
  const unixVenv = path.join(backendDir, ".venv", "bin", "python");
  if (process.platform === "win32" && existsSync(winVenv)) {
    return { command: winVenv, prefixArgs: [] };
  }
  if (existsSync(unixVenv3)) {
    return { command: unixVenv3, prefixArgs: [] };
  }
  if (existsSync(unixVenv)) {
    return { command: unixVenv, prefixArgs: [] };
  }
  if (process.platform === "win32") {
    const pyProbe = spawnSync("py", ["-3", "--version"], {
      cwd: backendDir,
      stdio: "ignore",
      shell: false,
    });
    if (pyProbe.status === 0) {
      return { command: "py", prefixArgs: ["-3"] };
    }
    return { command: "python", prefixArgs: [] };
  }
  return { command: "python3", prefixArgs: [] };
}

const { apiHost, apiPort: portFromFile } = readPorts();
const apiPort = process.env.MEDIAMOP_DEV_API_PORT?.trim()
  ? Number(process.env.MEDIAMOP_DEV_API_PORT.trim())
  : Number(portFromFile);

const pythonCmd = resolvePythonCmd();
const uvicornArgs = [
  ...pythonCmd.prefixArgs,
  "-m",
  "uvicorn",
  "mediamop.api.main:app",
  "--host",
  apiHost,
  "--port",
  String(apiPort),
  "--reload",
];

const child = spawn(pythonCmd.command, uvicornArgs, {
  cwd: backendDir,
  stdio: "inherit",
  env: {
    ...process.env,
    PYTHONPATH: "src",
    MEDIAMOP_HOME: (process.env.MEDIAMOP_HOME || "").trim() || defaultDevHome,
    MEDIAMOP_SESSION_SECRET:
      (process.env.MEDIAMOP_SESSION_SECRET || "").trim() || defaultDevSessionSecret,
  },
  shell: false,
});

function forward(signal) {
  try {
    child.kill(signal);
  } catch {
    /* ignore */
  }
}

process.on("SIGINT", () => forward("SIGINT"));
process.on("SIGTERM", () => forward("SIGTERM"));

child.on("exit", (code, signal) => {
  if (signal) {
    process.exit(1);
  }
  process.exit(code ?? 0);
});
