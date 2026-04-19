#!/usr/bin/env node
/**
 * Starts the MediaMop API, waits until it actually serves traffic, then starts Vite.
 * Avoids the browser hitting the proxy before uvicorn has finished lifespan/migrations
 * (which produced HTTP 500 / "Cannot reach the API" on every dev refresh).
 *
 * If something (e.g. a Cursor terminal) already left uvicorn listening on the dev API port
 * with a healthy ``/health``, we **reuse** it and only start Vite — otherwise a second API
 * would bind-fail and the web UI would not come up. (``npm run dev`` in ``package.json`` stops
 * the default API/web ports first so a leftover process is not reused by accident.)
 * Set ``MEDIAMOP_DEV_STACK_ALWAYS_SPAWN_API=1`` to force spawning the API child anyway.
 *
 * If ``GET /api/v1/subber/library/sync/movies`` returns **404** while ``/health`` works, the
 * default port usually holds an **older** MediaMop build (current code answers **405**). We then
 * start this repo's API on the **next free TCP port** and set ``MEDIAMOP_DEV_STACK_API_PROXY_TARGET``
 * for Vite so the UI still works without manually killing the stale process.
 *
 * If the **web** port from ``dev-ports.json`` is busy (leftover Vite), the next free port is used
 * and ``MEDIAMOP_DEV_WEB_PORT`` is set for Vite (see ``vite.config.ts``). Run ``npm run dev:stop-web``
 * to free the default port, or use the URL printed in the log.
 *
 * The API validates browser ``Origin``/``Referer`` against ``MEDIAMOP_TRUSTED_BROWSER_ORIGINS`` or
 * ``MEDIAMOP_CORS_ORIGINS``. ``localhost`` and ``127.0.0.1`` are different origins, so this script
 * merges both into the spawned API env to avoid ``403 Origin not allowed`` on login.
 */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
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

/** ``http://127.0.0.1:<port>`` and ``http://localhost:<port>`` (browsers treat these as distinct). */
function devWebBrowserOrigins(webPort) {
  return [`http://127.0.0.1:${webPort}`, `http://localhost:${webPort}`];
}

function mergeCsvUrlEnv(existingCsv, additions) {
  const seen = new Set();
  const out = [];
  const push = (raw) => {
    const s = String(raw || "").trim();
    if (!s || seen.has(s)) {
      return;
    }
    seen.add(s);
    out.push(s);
  };
  for (const part of String(existingCsv || "").split(",")) {
    push(part);
  }
  for (const a of additions) {
    push(a);
  }
  return out.join(",");
}

/**
 * Ensures the dev UI origin (both hostname spellings) is trusted and allowed by CORS for the
 * spawned API child process.
 */
function buildApiDevOriginEnvPatch(webPort) {
  const extra = devWebBrowserOrigins(webPort);
  const cors = mergeCsvUrlEnv(process.env.MEDIAMOP_CORS_ORIGINS, extra);
  const patch = { MEDIAMOP_CORS_ORIGINS: cors };
  const trustedRaw = (process.env.MEDIAMOP_TRUSTED_BROWSER_ORIGINS || "").trim();
  if (trustedRaw.length > 0) {
    patch.MEDIAMOP_TRUSTED_BROWSER_ORIGINS = mergeCsvUrlEnv(process.env.MEDIAMOP_TRUSTED_BROWSER_ORIGINS, extra);
  }
  return patch;
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
 * POST-only Subber route: a **current** FastAPI app responds with **405** to GET; an older
 * build without the route returns **404**. Used to avoid reusing a stale uvicorn on the dev port.
 */
function probeSubberLibrarySyncMoviesRouteNotStale(apiHost, apiPort) {
  const { hostname, port } = apiConnectTarget(apiHost, apiPort);
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname,
        port,
        path: "/api/v1/subber/library/sync/movies",
        method: "GET",
        timeout: 3000,
      },
      (res) => {
        res.resume();
        if (res.statusCode === 404) {
          resolve(false);
          return;
        }
        resolve(true);
      },
    );
    req.on("error", () => {
      console.error(
        "[dev-stack] Could not probe Subber library sync route (network error) — assuming API is OK.",
      );
      resolve(true);
    });
    req.on("timeout", () => {
      req.destroy();
      console.error(
        "[dev-stack] Timed out probing Subber library sync route — assuming API is OK.",
      );
      resolve(true);
    });
    req.end();
  });
}

/**
 * First port in ``[startPort, inclusiveMax]`` with nothing answering ``/health`` like our API
 * probe (frees the slot for a new uvicorn).
 */
async function findFirstTcpPortWithoutHealthyApi(apiHost, startPort, inclusiveMax) {
  for (let p = startPort; p <= inclusiveMax; p += 1) {
    if (!(await probeApiAlreadyServing(apiHost, p))) {
      return p;
    }
  }
  return null;
}

/** True if nothing is listening (we can bind a dev server). */
function canBindHostPort(hostname, port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    const finish = (ok) => {
      srv.removeAllListeners("error");
      srv.close(() => resolve(ok));
    };
    srv.once("error", () => finish(false));
    srv.listen(port, hostname, () => finish(true));
  });
}

async function resolveDevWebPort(webHost, configuredPort) {
  const { hostname } = apiConnectTarget(webHost, configuredPort);
  const max = Math.min(configuredPort + 40, 65535);
  for (let p = configuredPort; p <= max; p += 1) {
    if (await canBindHostPort(hostname, p)) {
      if (p !== configuredPort) {
        console.error(
          `[dev-stack] Web port ${configuredPort} is already in use — starting Vite on ${p}. ` +
            `Open http://127.0.0.1:${p}/ (or run \`npm run dev:stop-web\` and use ${configuredPort}).`,
        );
      }
      return p;
    }
  }
  console.error(
    `[dev-stack] No free TCP port for Vite between ${configuredPort} and ${max}. ` +
      `From apps/web run:  npm run dev:stop-web`,
  );
  process.exit(1);
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
const { apiHost, apiPort: portFromFile, webHost, webPort: configuredWebPort } = readDevPorts();
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
  const healthOk = await probeApiAlreadyServing(apiHost, apiPort);
  let subberRoutesOk = true;
  if (healthOk) {
    subberRoutesOk = await probeSubberLibrarySyncMoviesRouteNotStale(apiHost, apiPort);
  }
  /** Stale build on the configured port: would make Subber library sync POST return 404. */
  const staleDefaultApi = healthOk && !subberRoutesOk;

  let bindPort = apiPort;
  /** When set, Vite must proxy ``/api`` here (see ``vite.config.ts``). */
  let viteProxyOverride = "";

  if (staleDefaultApi) {
    const { hostname, port: stalePort } = apiConnectTarget(apiHost, apiPort);
    const maxPort = Math.min(apiPort + 40, 65535);
    const found = await findFirstTcpPortWithoutHealthyApi(apiHost, apiPort + 1, maxPort);
    if (found == null) {
      console.error(
        `[dev-stack] http://${hostname}:${stalePort} is an outdated MediaMop API (Subber sync route missing). ` +
          `No free port found between ${apiPort + 1} and ${maxPort} for a new API.\n` +
          `[dev-stack] Free a port or stop the old process, then run npm run dev again.`,
      );
      process.exit(1);
    }
    bindPort = found;
    const { hostname: bindHost, port: bindProbePort } = apiConnectTarget(apiHost, bindPort);
    viteProxyOverride = `http://${bindHost}:${bindProbePort}`;
    console.error(
      `[dev-stack] Port ${stalePort} has an older MediaMop API build. Starting this repo's API on ` +
        `${bindProbePort} and proxying /api there (close the old terminal when convenient).`,
    );
  }

  const chosenWebPort = await resolveDevWebPort(webHost, configuredWebPort);
  const apiOriginEnvPatch = buildApiDevOriginEnvPatch(chosenWebPort);

  const canReuse = !forceSpawn && healthOk && subberRoutesOk;

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
      env: { ...process.env, ...apiOriginEnvPatch, MEDIAMOP_DEV_API_PORT: String(bindPort) },
    });

    await waitForApiHttpReady(api, { apiHost, apiPort: bindPort, timeoutMs: waitMs });
  }

  const viteEnv =
    viteProxyOverride.trim().length > 0
      ? { ...process.env, MEDIAMOP_DEV_STACK_API_PROXY_TARGET: viteProxyOverride.trim() }
      : { ...process.env };

  const viteEnvWithPort = { ...viteEnv, MEDIAMOP_DEV_WEB_PORT: String(chosenWebPort) };

  web = spawn(node, [viteEntry], {
    cwd: webDir,
    stdio: "inherit",
    env: viteEnvWithPort,
  });

  await waitForWebHttpReady(web, api, { webHost, webPort: chosenWebPort, timeoutMs: webWaitMs });

  console.error(`[dev-stack] Web UI (open when ready): http://127.0.0.1:${chosenWebPort}/`);
  console.error(`[dev-stack] Same UI via localhost:     http://localhost:${chosenWebPort}/`);
  if (viteProxyOverride.trim().length > 0) {
    console.error(`[dev-stack] Vite /api → ${viteProxyOverride.trim()} (default port still has an old API).`);
  }

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
