/**
 * Browser API client — cookie session auth with ``credentials: 'include'``.
 * No localStorage tokens; backend ``UserSession`` + cookie are authoritative.
 */

const API_PREFIX = "/api/v1";
const DEFAULT_TIMEOUT_MS = 30_000;
type UnauthorizedHandler = (path: string) => void;

export type ApiFetchInit = RequestInit & {
  timeoutMs?: number;
};

export class ApiHttpError extends Error {
  readonly status: number;
  readonly path: string;
  readonly detail: unknown;
  readonly timedOut: boolean;

  constructor(path: string, status: number, message: string, detail?: unknown, timedOut = false) {
    super(message);
    this.name = "ApiHttpError";
    this.status = status;
    this.path = path;
    this.detail = detail;
    this.timedOut = timedOut;
  }
}

let unauthorizedHandler: UnauthorizedHandler | null = null;
let unauthorizedHandled = false;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
  unauthorizedHandled = false;
}

export function resetUnauthorizedHandlingForTests(): void {
  unauthorizedHandler = null;
  unauthorizedHandled = false;
}

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

function buildTimeoutSignal(timeoutMs: number): AbortSignal | null {
  if (typeof AbortSignal === "undefined") {
    return null;
  }
  if (typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(timeoutMs);
  }
  return null;
}

function combineSignals(callerSignal: AbortSignal | null | undefined, timeoutSignal: AbortSignal | null): AbortSignal | null {
  if (callerSignal && timeoutSignal && typeof AbortSignal.any === "function") {
    return AbortSignal.any([callerSignal, timeoutSignal]);
  }
  return callerSignal ?? timeoutSignal;
}

function isTimeoutAbort(error: unknown, timeoutSignal: AbortSignal | null): boolean {
  if (!error || typeof error !== "object" || !("name" in error) || error.name !== "AbortError") {
    return false;
  }
  return Boolean(timeoutSignal?.aborted);
}

export async function apiFetch(path: string, init?: ApiFetchInit): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: callerSignal, ...requestInit } = init ?? {};
  const timeoutSignal = buildTimeoutSignal(timeoutMs);
  const signal = combineSignals(callerSignal ?? null, timeoutSignal);
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...requestInit,
      credentials: "include",
      signal: signal ?? undefined,
      headers: {
        Accept: "application/json",
        ...requestInit.headers,
      },
    });
  } catch (error) {
    if (isTimeoutAbort(error, timeoutSignal)) {
      throw new ApiHttpError(
        path,
        0,
        "Request timed out - the backend may be slow or unreachable.",
        undefined,
        true,
      );
    }
    throw error;
  }
  if (response.status === 401 && unauthorizedHandler && !unauthorizedHandled) {
    unauthorizedHandled = true;
    unauthorizedHandler(path);
  }
  if (response.status !== 401) {
    unauthorizedHandled = false;
  }
  return response;
}

export async function readJson<T>(r: Response): Promise<T> {
  const text = await r.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

function messageFromResponseBody(body: unknown): { message: string; detail?: unknown } {
  if (body === undefined || body === null) {
    return { message: "" };
  }
  if (typeof body === "string") {
    return { message: body.trim() };
  }
  if (typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    return { message: apiErrorDetailToString(detail), detail };
  }
  return { message: apiErrorDetailToString(body), detail: body };
}

export async function apiResponseErrorMessage(r: Response, fallback: string): Promise<{ message: string; detail?: unknown }> {
  const ctype = (r.headers.get("content-type") || "").toLowerCase();
  if (ctype.includes("application/json")) {
    try {
      const parsed = await r.clone().json();
      const fromBody = messageFromResponseBody(parsed);
      if (fromBody.message.length > 0) {
        return fromBody;
      }
    } catch {
      /* fall through to text/status fallback */
    }
  }

  let text = "";
  try {
    text = await r.clone().text();
  } catch {
    text = "";
  }
  const trimmed = text.trimStart();
  if (trimmed.startsWith("<!") || trimmed.toLowerCase().startsWith("<html")) {
    return {
      message: `${fallback} (${r.status}) - received HTML instead of JSON. Use the same origin as the API and restart MediaMop after upgrading.`,
    };
  }
  const oneLine = text.replace(/\s+/g, " ").trim().slice(0, 180);
  if (oneLine.length > 0) {
    return { message: `${fallback} (${r.status}): ${oneLine}` };
  }
  return { message: `${fallback} (${r.status})` };
}

export async function throwApiResponseError(path: string, r: Response, fallback: string): Promise<never> {
  const normalized = await apiResponseErrorMessage(r, fallback);
  throw new ApiHttpError(path, r.status, normalized.message, normalized.detail);
}

export async function requireOk(path: string, r: Response, fallback: string): Promise<void> {
  if (!r.ok) {
    await throwApiResponseError(path, r, fallback);
  }
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
