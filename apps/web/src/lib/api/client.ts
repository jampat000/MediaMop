/**
 * Browser API client — cookie session auth with ``credentials: 'include'``.
 * No localStorage tokens; backend ``UserSession`` + cookie are authoritative.
 */

const API_PREFIX = "/api/v1";

function baseUrl(): string {
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
