import { ApiHttpError } from "./client";

/**
 * Classify failures from auth API helpers ({@link ./auth-api}) for honest UI copy.
 * `fetch` only throws TypeError (or "Failed to fetch") when the response never arrived.
 */

export function isLikelyNetworkFailure(error: unknown): boolean {
  // `apiFetch` (client.ts) already classifies its own `fetch` rejections at the source and
  // rethrows them as an `ApiHttpError` carrying the friendly message — check that marker
  // first so every screen built on `apiFetch` gets it without re-deriving the classification.
  if (error instanceof ApiHttpError) {
    return error.networkUnreachable;
  }
  if (error instanceof TypeError) {
    return true;
  }
  if (!(error instanceof Error)) {
    return false;
  }
  const m = error.message;
  return (
    m === "Failed to fetch" ||
    m.includes("NetworkError") ||
    m.includes("Load failed") ||
    m.includes("Failed to retrieve")
  );
}

const _API_HTTP_ERR = /^(bootstrap status|me|CSRF|activity recent): (\d{3})\b/;

/** True when {@link ./auth-api} threw after receiving an HTTP status (API was reached). */
export function isHttpErrorFromApi(error: unknown): boolean {
  if (error instanceof ApiHttpError) {
    return true;
  }
  if (!(error instanceof Error)) {
    return false;
  }
  return _API_HTTP_ERR.test(error.message);
}

export function httpStatusFromApiError(error: unknown): number | null {
  if (error instanceof ApiHttpError) {
    return error.status;
  }
  if (!(error instanceof Error)) {
    return null;
  }
  const m = error.message.match(_API_HTTP_ERR);
  return m ? Number(m[2]) : null;
}

/**
 * In `vite dev`, proxied `/api/*` requests that cannot reach the backend (ECONNREFUSED) still
 * produce an HTTP response — the dev server typically returns **500** with an empty/plain body.
 * The real API avoids 500 on guest-first routes (e.g. bootstrap uses 503 for DB issues), so
 * 500 + relative API URLs in development is almost always "API process not listening".
 */
export function isLikelyViteProxyUpstreamDown(error: unknown): boolean {
  if (!import.meta.env.DEV) {
    return false;
  }
  return isHttpErrorFromApi(error) && httpStatusFromApiError(error) === 500;
}
