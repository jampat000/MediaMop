#!/usr/bin/env node
/**
 * Spawns the MediaMop API like `scripts/dev-backend.ps1` (cwd apps/backend, PYTHONPATH=src,
 * host/port from scripts/dev-ports.json). Used by `npm run dev` so Vite and uvicorn start together.
 */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.join(__dirname, "..");
const repoRoot = path.resolve(webDir, "..", "..");
const backendDir = path.join(repoRoot, "apps", "backend");
const portsPath = path.join(repoRoot, "scripts", "dev-ports.json");

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
    return winVenv;
  }
  if (existsSync(unixVenv3)) {
    return unixVenv3;
  }
  if (existsSync(unixVenv)) {
    return unixVenv;
  }
  if (process.platform === "win32") {
    return "python";
  }
  return "python3";
}

const { apiHost, apiPort: portFromFile } = readPorts();
const apiPort = process.env.MEDIAMOP_DEV_API_PORT?.trim()
  ? Number(process.env.MEDIAMOP_DEV_API_PORT.trim())
  : Number(portFromFile);

const pythonCmd = resolvePythonCmd();
const uvicornArgs = [
  "-m",
  "uvicorn",
  "mediamop.api.main:app",
  "--host",
  apiHost,
  "--port",
  String(apiPort),
  "--reload",
];

const child = spawn(pythonCmd, uvicornArgs, {
  cwd: backendDir,
  stdio: "inherit",
  env: { ...process.env, PYTHONPATH: "src" },
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
