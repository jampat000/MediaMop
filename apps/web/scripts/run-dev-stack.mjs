#!/usr/bin/env node
/**
 * Starts the MediaMop API, waits until it actually serves traffic, then starts Vite.
 * Avoids the browser hitting the proxy before uvicorn has finished lifespan/migrations
 * (which produced HTTP 500 / "Cannot reach the API" on every dev refresh).
 */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.join(__dirname, "..");
const repoRoot = path.resolve(webDir, "..", "..");
const apiScript = path.join(__dirname, "run-api-dev.mjs");
const viteEntry = path.join(webDir, "node_modules", "vite", "bin", "vite.js");
const portsPath = path.join(repoRoot, "scripts", "dev-ports.json");

if (!existsSync(viteEntry)) {
  console.error(`Missing ${viteEntry}. Run npm install (or npm ci) in apps/web.`);
  process.exit(1);
}

function readDevPorts() {
  const raw = readFileSync(portsPath, "utf8");
  return JSON.parse(raw).development;
}

function apiConnectTarget(apiHost, apiPort) {
  const host =
    apiHost === "0.0.0.0" || apiHost === "::" || apiHost === "[::]" ? "127.0.0.1" : apiHost;
  return { hostname: host, port: apiPort };
}

/**
 * @param {import('node:child_process').ChildProcess} apiChild
 */
async function waitForApiHttpReady(apiChild, { apiHost, apiPort, timeoutMs }) {
  const { hostname, port } = apiConnectTarget(apiHost, apiPort);
  const start = Date.now();
  let lastLog = 0;

  console.error(
    `[dev-stack] Waiting for API at http://${hostname}:${port}/health (migrations can take a few seconds)…`,
  );

  while (Date.now() - start < timeoutMs) {
    if (apiChild.exitCode !== null) {
      console.error(
        "[dev-stack] API exited before startup finished. Fix errors above (venv, " +
          "MEDIAMOP_SESSION_SECRET, SQLite path, or Alembic). If you see duplicate-column errors " +
          "after splitting migration 0041/0042, pull latest backend and run migrations again.",
      );
      process.exit(1);
    }

    const ok = await new Promise((resolve) => {
      const req = http.request(
        {
          hostname,
          port,
          path: "/health",
          method: "GET",
          timeout: 2000,
        },
        (res) => {
          res.resume();
          resolve(res.statusCode !== undefined && res.statusCode >= 200 && res.statusCode < 500);
        },
      );
      req.on("error", () => resolve(false));
      req.on("timeout", () => {
        req.destroy();
        resolve(false);
      });
      req.end();
    });

    if (ok) {
      console.error(`[dev-stack] API is ready — starting Vite…`);
      return;
    }

    const elapsed = Date.now() - start;
    if (elapsed - lastLog > 5000) {
      console.error(`[dev-stack] Still waiting (${Math.round(elapsed / 1000)}s / ${Math.round(timeoutMs / 1000)}s)…`);
      lastLog = elapsed;
    }
    await new Promise((r) => setTimeout(r, 300));
  }

  console.error(
    `[dev-stack] Timed out after ${timeoutMs / 1000}s waiting for http://${hostname}:${port}/health.`,
  );
  try {
    apiChild.kill("SIGTERM");
  } catch {
    /* ignore */
  }
  process.exit(1);
}

const node = process.execPath;
const { apiHost, apiPort: portFromFile, webHost, webPort } = readDevPorts();
const apiPort = process.env.MEDIAMOP_DEV_API_PORT?.trim()
  ? Number(process.env.MEDIAMOP_DEV_API_PORT.trim())
  : Number(portFromFile);

let api = null;
let web = null;
let stopping = false;

function forwardStop(signal) {
  try {
    web?.kill(signal);
  } catch {
    /* ignore */
  }
  try {
    api?.kill(signal);
  } catch {
    /* ignore */
  }
}

process.on("SIGINT", () => forwardStop("SIGINT"));
process.on("SIGTERM", () => forwardStop("SIGTERM"));

function wireExit(name, child, other) {
  child.on("exit", (code, signal) => {
    if (stopping) {
      return;
    }
    stopping = true;
    try {
      if (other && !other.killed) {
        other.kill("SIGTERM");
      }
    } catch {
      /* ignore */
    }
    if (code !== 0 && code !== null) {
      console.error(`[${name}] exited with code ${code}${signal ? ` (${signal})` : ""}.`);
    }
    if (signal) {
      process.exit(1);
    }
    process.exit(code ?? 0);
  });
}

const waitMs = Number(process.env.MEDIAMOP_DEV_STACK_API_WAIT_MS || 120000);

async function main() {
  api = spawn(node, [apiScript], {
    cwd: webDir,
    stdio: "inherit",
    env: { ...process.env },
  });

  await waitForApiHttpReady(api, { apiHost, apiPort, timeoutMs: waitMs });

  web = spawn(node, [viteEntry], {
    cwd: webDir,
    stdio: "inherit",
    env: { ...process.env },
  });

  console.error(`[dev-stack] Web UI: http://${webHost}:${webPort}/`);

  wireExit("api", api, web);
  wireExit("web", web, api);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
