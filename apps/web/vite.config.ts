import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const packageJson = JSON.parse(
  readFileSync(path.join(__dirname, "package.json"), "utf-8"),
) as { version: string };

type DevPortsFile = {
  development: {
    webHost: string;
    webPort: number;
    apiHost: string;
    apiPort: number;
  };
};

const devPortsPath = path.join(
  __dirname,
  "..",
  "..",
  "scripts",
  "dev-ports.json",
);
const devPorts = JSON.parse(
  readFileSync(devPortsPath, "utf-8"),
) as DevPortsFile;
const dev = devPorts.development;

/** ``run-dev-stack.mjs`` may bump the port when the default from ``dev-ports.json`` is busy. */
const devWebPort = (() => {
  const raw = (process.env.MEDIAMOP_DEV_WEB_PORT || "").trim();
  if (raw) {
    const n = Number(raw);
    if (Number.isFinite(n) && n >= 1 && n <= 65535) {
      return n;
    }
  }
  return dev.webPort;
})();

function apiProxyTarget(mode: string, envDir: string): string {
  // Takes precedence over .env* (loadEnv) so automation can pin /api to a known backend.
  const forced = (
    process.env.MEDIAMOP_SCREENSHOT_API_PROXY_TARGET || ""
  ).trim();
  if (forced) {
    return forced;
  }
  // ``run-dev-stack.mjs`` sets this when the default API port holds an outdated build but a
  // fresh uvicorn is started on another port (see stale Subber route probe).
  const devStackProxy = (
    process.env.MEDIAMOP_DEV_STACK_API_PROXY_TARGET || ""
  ).trim();
  if (devStackProxy) {
    return devStackProxy;
  }
  const fromFiles = loadEnv(mode, envDir, "");
  const fallback = `http://${dev.apiHost}:${dev.apiPort}`;
  return (
    fromFiles.VITE_DEV_API_PROXY_TARGET ||
    process.env.VITE_DEV_API_PROXY_TARGET ||
    fallback
  );
}

export default defineConfig(({ mode }) => {
  const apiTarget = apiProxyTarget(mode, __dirname);

  const apiProxy = {
    "/api": {
      target: apiTarget,
      changeOrigin: true,
    },
    "/ready": {
      target: apiTarget,
      changeOrigin: true,
    },
    "/health": {
      target: apiTarget,
      changeOrigin: true,
    },
  };

  return {
    define: {
      __WEB_PACKAGE_VERSION__: JSON.stringify(packageJson.version),
    },
    plugins: [react()],
    build: {
      sourcemap: "hidden",
    },
    server: {
      // ``true`` = listen on all interfaces (0.0.0.0). Required so **http://localhost:<port>**
      // works on Windows: ``localhost`` often resolves to ``::1`` (IPv6) while binding only
      // ``127.0.0.1`` leaves IPv6 loopback with nothing listening → ERR_CONNECTION_REFUSED.
      // ``http://127.0.0.1:<port>`` still works. Default port from ``dev-ports.json`` unless overridden.
      host: true,
      port: devWebPort,
      strictPort: true,
      proxy: { ...apiProxy },
    },
    /** Same-origin cookies in dev/preview: browser hits the Vite port; /api is forwarded. */
    preview: {
      host: true,
      port: devWebPort,
      strictPort: true,
      proxy: { ...apiProxy },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      globals: true,
    },
  };
});
