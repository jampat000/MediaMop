/**
 * Detects a sign-in that succeeded but did not stick (#453).
 *
 * A browser can accept a 200 from `/auth/login` and then discard the session cookie — most often
 * because the cookie is marked `Secure` while Weir is served over plain HTTP. The next call
 * to `/auth/me` returns 401, `RequireAuth` redirects, and the operator lands back on an empty
 * form with a correct password and nothing explaining why.
 *
 * The app knows both halves of that, so it can say so. This records the successful sign-in for a
 * few seconds; `RequireAuth` reads it when `/auth/me` comes back empty and sends the operator to
 * the login page with a reason instead of silently.
 */

const KEY = "mm:login-succeeded-at";

/** How long after a success a 401 still implies the cookie was dropped rather than expired. */
const WINDOW_MS = 10_000;

function store(): Storage | null {
  // Private windows and blocked site data make this throw rather than return null.
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function markLoginSucceeded(): void {
  try {
    store()?.setItem(KEY, String(Date.now()));
  } catch {
    /* A missing breadcrumb only costs us the nicer error message. */
  }
}

export function clearLoginSucceeded(): void {
  try {
    store()?.removeItem(KEY);
  } catch {
    /* ignored */
  }
}

/**
 * True when a sign-in succeeded moments ago yet the session is not usable — i.e. the cookie was
 * rejected. Consumes the marker so the message is shown once.
 */
export function sessionWasNotKept(now: number = Date.now()): boolean {
  const raw = (() => {
    try {
      return store()?.getItem(KEY) ?? null;
    } catch {
      return null;
    }
  })();

  if (raw === null) {
    return false;
  }
  clearLoginSucceeded();

  const at = Number(raw);
  if (!Number.isFinite(at)) {
    return false;
  }
  return now - at >= 0 && now - at < WINDOW_MS;
}
