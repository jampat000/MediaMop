#!/usr/bin/env node
/**
 * Spawns the Weir .NET server like `scripts/dev-backend.ps1` (`dotnet watch run` on
 * apps/server/src/Weir.Host, host/port from scripts/dev-ports.json). Used by `npm run dev` so Vite
 * and the API start together. The server creates or migrates its own SQLite database on start.
 *
 * Records the spawned PID (and how to recognise it) in `.dev-api.pid` at the repo root so
 * `scripts/stop-dev-api-port.mjs` can stop *this* process later — never "whatever holds the
 * port", which would kill an installed Weir if one happens to be listening on the same port
 * (see that script's header for why).
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.join(__dirname, "..");
const repoRoot = path.resolve(webDir, "..", "..");
const serverProject = path.join(repoRoot, "apps", "server", "src", "Weir.Host");
const portsPath = path.join(repoRoot, "scripts", "dev-ports.json");
const envFilePath = path.join(repoRoot, ".env");
const defaultDevHome = path.join(repoRoot, ".local-dev-home");
const defaultDevSessionSecret = "dev-session-secret-32-chars-minimum!!";
const pidFilePath = path.join(repoRoot, ".dev-api.pid");

function removePidFile() {
  try {
    rmSync(pidFilePath, { force: true });
  } catch {
    /* ignore — best-effort cleanup */
  }
}

function readPorts() {
  const raw = readFileSync(portsPath, "utf8");
  const j = JSON.parse(raw);
  return j.development;
}

/** The repository `.env` (KEY=value lines); variables already in the environment win. */
function readDotEnv() {
  if (!existsSync(envFilePath)) {
    return {};
  }
  const values = {};
  for (const rawLine of readFileSync(envFilePath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      value.length >= 2 &&
      ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'")))
    ) {
      value = value.slice(1, -1);
    }
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) values[key] = value;
  }
  return values;
}

const dotnetProbe = spawnSync("dotnet", ["--version"], { stdio: "ignore", shell: false });
if (dotnetProbe.error || dotnetProbe.status !== 0) {
  console.error(
    "[dev-api] The .NET 10 SDK is required to run the API (dotnet was not found). " +
      "See docs/local-development.md.",
  );
  process.exit(1);
}

const { apiHost, apiPort: portFromFile } = readPorts();
const apiPort = process.env.WEIR_DEV_API_PORT?.trim()
  ? Number(process.env.WEIR_DEV_API_PORT.trim())
  : Number(portFromFile);

const fromFile = readDotEnv();
const childEnv = { ...fromFile };
for (const [key, value] of Object.entries(process.env)) {
  if (value !== undefined && value.trim() !== "") childEnv[key] = value;
}
childEnv.WEIR_HOME = (childEnv.WEIR_HOME || "").trim() || defaultDevHome;
childEnv.WEIR_SESSION_SECRET =
  (childEnv.WEIR_SESSION_SECRET || "").trim() || defaultDevSessionSecret;

const child = spawn(
  "dotnet",
  [
    "watch",
    "run",
    "--project",
    serverProject,
    "--",
    "--host",
    apiHost,
    "--port",
    String(apiPort),
  ],
  {
    cwd: repoRoot,
    stdio: "inherit",
    env: childEnv,
    shell: false,
    // Unix only: makes `child` the leader of its own process group so
    // stop-dev-api-port.mjs can stop `dotnet watch`'s children (the actual `dotnet exec` that
    // binds the port) along with it, not just the watcher. Windows tracks the parent/child
    // lineage itself, so `taskkill /T` there needs no flag on spawn.
    detached: process.platform !== "win32",
  },
);

// Recorded so stop-dev-api-port.mjs can find and verify *this* process later, instead of
// stopping whatever else happens to be listening on the port (which could be an installed
// Weir — see that script's header).
writeFileSync(
  pidFilePath,
  JSON.stringify(
    {
      pid: child.pid,
      // `dotnet` is a generic launcher shared by every .NET process on the machine; the
      // project path is what actually identifies *this* dev API, the same way the installer
      // only recognises a Weir process whose executable is inside its own install folder
      // (apps/tray/Weir.Tray/InstallProcesses.cs).
      serverProject,
      apiHost,
      apiPort,
      startedAt: new Date().toISOString(),
    },
    null,
    2,
  ),
);

function forward(signal) {
  try {
    child.kill(signal);
  } catch {
    /* ignore */
  }
}

process.on("SIGINT", () => forward("SIGINT"));
process.on("SIGTERM", () => forward("SIGTERM"));
process.on("exit", removePidFile);

child.on("exit", (code, signal) => {
  removePidFile();
  if (signal) {
    process.exit(1);
  }
  process.exit(code ?? 0);
});
