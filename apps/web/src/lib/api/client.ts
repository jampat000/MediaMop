/**
 * Browser API client — cookie session auth with ``credentials: 'include'``.
 * No localStorage tokens; backend ``UserSession`` + cookie are authoritative.
 */

const API_PREFIX = "/api/v1";

function baseUrl(): string {
  // In ``vite dev``, always use same-origin ``/api`` so the dev proxy applies (including
  // ``MEDIAMOP_DEV_STACK_API_PROXY_TARGET`` when the API moved to a fallback port). A pinned
  // ``VITE_API_BASE_URL=http://127.0.0.1:8788`` in ``.env`` would otherwise bypass the proxy and
  // keep talking to an old uvicorn on 8788 while the new API listens on 8789 — Subber sync 404s.
  if (import.meta.env.DEV) {
    return "";
  }
  const raw = import.meta.env.VITE_API_BASE_URL?.trim();
  return raw ? raw.replace(/\/$/, "") : "";
}

export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  if (!p.startsWith(API_PREFIX)) {
    throw new Error(`API paths must be under ${API_PREFIX}`);
  }
  return `${baseUrl()}${p}`;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });
}

export async function readJson<T>(r: Response): Promise<T> {
  const text = await r.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

/**
 * FastAPI ``detail`` may be a string, a validation error array, or (rarely) a nested object.
 * Never pass ``detail`` straight into ``new Error()`` — non-strings become ``"[object Object]"``.
 */
export function apiErrorDetailToString(detail: unknown): string {
  if (detail === undefined || detail === null) {
    return "";
  }
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === "object" && item !== null && "msg" in item) {
        const o = item as { msg?: unknown; loc?: unknown };
        const m = o.msg;
        if (typeof m === "string") {
          const loc = Array.isArray(o.loc) ? o.loc.filter((x) => x !== "body").join(".") : "";
          return loc.length > 0 ? `${loc}: ${m}` : m;
        }
      }
      try {
        return JSON.stringify(item);
      } catch {
        return String(item);
      }
    });
    return parts.filter((s) => s.length > 0).join("; ");
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return "Request failed.";
    }
  }
  return String(detail);
}
