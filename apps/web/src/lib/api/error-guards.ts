/**
 * Classify failures from auth API helpers ({@link ./auth-api}) for honest UI copy.
 * `fetch` only throws TypeError (or "Failed to fetch") when the response never arrived.
 */

export function isLikelyNetworkFailure(error: unknown): boolean {
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

const _API_HTTP_ERR = /^(bootstrap status|me|CSRF|dashboard status): (\d{3})\b/;

/** True when {@link ./auth-api} threw after receiving an HTTP status (API was reached). */
export function isHttpErrorFromApi(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  return _API_HTTP_ERR.test(error.message);
}

export function httpStatusFromApiError(error: unknown): number | null {
  if (!(error instanceof Error)) {
    return null;
  }
  const m = error.message.match(_API_HTTP_ERR);
  return m ? Number(m[2]) : null;
}
