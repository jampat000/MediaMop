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

const devPortsPath = path.join(__dirname, "..", "..", "scripts", "dev-ports.json");
const devPorts = JSON.parse(readFileSync(devPortsPath, "utf-8")) as DevPortsFile;
const dev = devPorts.development;

function apiProxyTarget(mode: string, envDir: string): string {
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
  };

  return {
    define: {
      __WEB_PACKAGE_VERSION__: JSON.stringify(packageJson.version),
    },
    plugins: [react()],
    server: {
      // Bind IPv4 explicitly — on Windows the default can be [::1] only, so
      // opening http://127.0.0.1:<webPort> would get "connection refused".
      host: dev.webHost,
      port: dev.webPort,
      strictPort: true,
      proxy: { ...apiProxy },
    },
    /** Same-origin cookies in dev/preview: browser hits the Vite port; /api is forwarded. */
    preview: {
      host: dev.webHost,
      port: dev.webPort,
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
