/// <reference types="vite/client" />

/** Injected in ``vite.config.ts`` from ``package.json`` ``version``. */
declare const __WEB_PACKAGE_VERSION__: string;

interface ImportMetaEnv {
  /** Optional absolute origin for API (production). Dev default: same-origin via Vite ``/api`` proxy. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
