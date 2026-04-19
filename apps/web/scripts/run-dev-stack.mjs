#!/usr/bin/env node
/**
 * Starts the MediaMop API, waits until it actually serves traffic, then starts Vite.
 * Avoids the browser hitting the proxy before uvicorn has finished lifespan/migrations
 * (which produced HTTP 500 / "Cannot reach the API" on every dev refresh).
 *
 * If something (e.g. a Cursor terminal) already left uvicorn listening on the dev API port
 * with a healthy ``/health``, we **reuse** it and only start Vite — otherwise ``npm run dev``
 * spawns a second API, bind fails, and the web UI never comes up on 8782.
 * Set ``MEDIAMOP_DEV_STACK_ALWAYS_SPAWN_API=1`` to force spawning the API child anyway.
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

/** One-shot probe: same success rule as the API wait loop (2xx–4xx on ``/health``). */
function probeApiAlreadyServing(apiHost, apiPort) {
  const { hostname, port } = apiConnectTarget(apiHost, apiPort);
  return new Promise((resolve) => {
    const req = http.request(
      { hostname, port, path: "/health", method: "GET", timeout: 2000 },
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
}

/**
 * @param {object} opts
 * @param {string} opts.hostname
 * @param {number} opts.port
 * @param {string} opts.path
 * @param {string} opts.label
 * @param {number} opts.timeoutMs
 * @param {import("node:child_process").ChildProcess | null} [opts.child]
 * @param {import("node:child_process").ChildProcess[]} [opts.killOnTimeout]
 * @param {string} [opts.waitHint]
 */
async function waitForHttpOk(opts) {
  const { hostname, port, path, label, timeoutMs, child, killOnTimeout, waitHint } = opts;
  const start = Date.now();
  let lastLog = 0;
  const hint = waitHint ? ` ${waitHint}` : "";

  console.error(`[dev-stack] Waiting for ${label} at http://${hostname}:${port}${path}${hint}…`);

  while (Date.now() - start < timeoutMs) {
    if (child && child.exitCode !== null) {
      if (label.includes("API")) {
        console.error(
          "[dev-stack] API exited before startup finished. Fix errors above (venv, " +
            "MEDIAMOP_SESSION_SECRET, SQLite path, or Alembic). If you see duplicate-column errors " +
            "after splitting migration 0041/0042, pull latest backend and run migrations again.",
        );
      } else {
        console.error(`[dev-stack] ${label} exited before startup finished — see errors above.`);
      }
      process.exit(1);
    }

    const ok = await new Promise((resolve) => {
      const req = http.request(
        {
          hostname,
          port,
          path,
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
      console.error(`[dev-stack] ${label} is ready.`);
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
    `[dev-stack] Timed out after ${timeoutMs / 1000}s waiting for http://${hostname}:${port}${path}.`,
  );
  const toStop = killOnTimeout ?? (child ? [child] : []);
  for (const c of toStop) {
    try {
      c.kill("SIGTERM");
    } catch {
      /* ignore */
    }
  }
  process.exit(1);
}

async function waitForApiHttpReady(apiChild, { apiHost, apiPort, timeoutMs }) {
  const { hostname, port } = apiConnectTarget(apiHost, apiPort);
  await waitForHttpOk({
    hostname,
    port,
    path: "/health",
    label: "API",
    timeoutMs,
    child: apiChild,
    killOnTimeout: [apiChild],
    waitHint: "(migrations can take a few seconds)",
  });
  console.error(`[dev-stack] API is ready — starting Vite…`);
}

async function waitForWebHttpReady(webChild, apiChild, { webHost, webPort, timeoutMs }) {
  const probeHost =
    webHost === "0.0.0.0" || webHost === "::" || webHost === "[::]" ? "127.0.0.1" : webHost;
  const killOnTimeout = [webChild, apiChild].filter((c) => c != null);
  await waitForHttpOk({
    hostname: probeHost,
    port: webPort,
    path: "/",
    label: "Vite (web)",
    timeoutMs,
    child: webChild,
    killOnTimeout,
    waitHint: "(first compile can take a few seconds)",
  });
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
const webWaitMs = Number(process.env.MEDIAMOP_DEV_STACK_WEB_WAIT_MS || 120000);

async function main() {
  const forceSpawn = (process.env.MEDIAMOP_DEV_STACK_ALWAYS_SPAWN_API || "").trim() === "1";
  const canReuse = !forceSpawn && (await probeApiAlreadyServing(apiHost, apiPort));

  if (canReuse) {
    const { hostname, port } = apiConnectTarget(apiHost, apiPort);
    console.error(
      `[dev-stack] API already serving at http://${hostname}:${port}/health — skipping API spawn. ` +
        `Starting Vite only. (Set MEDIAMOP_DEV_STACK_ALWAYS_SPAWN_API=1 to spawn a new API.)`,
    );
    api = null;
  } else {
    api = spawn(node, [apiScript], {
      cwd: webDir,
      stdio: "inherit",
      env: { ...process.env },
    });

    await waitForApiHttpReady(api, { apiHost, apiPort, timeoutMs: waitMs });
  }

  web = spawn(node, [viteEntry], {
    cwd: webDir,
    stdio: "inherit",
    env: { ...process.env },
  });

  await waitForWebHttpReady(web, api, { webHost, webPort, timeoutMs: webWaitMs });

  console.error(`[dev-stack] Web UI (open when ready): http://127.0.0.1:${webPort}/`);
  console.error(`[dev-stack] Same UI via localhost:     http://localhost:${webPort}/`);

  if (api) {
    wireExit("api", api, web);
    wireExit("web", web, api);
  } else {
    wireExit("web", web, null);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
