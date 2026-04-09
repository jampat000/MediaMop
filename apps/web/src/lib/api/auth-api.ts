import { apiFetch, readJson } from "./client";
import type { BootstrapStatus, UserPublic } from "./types";

export async function fetchCsrfToken(): Promise<string> {
  const r = await apiFetch("/api/v1/auth/csrf");
  if (!r.ok) {
    throw new Error(`CSRF: ${r.status}`);
  }
  const data = await readJson<{ csrf_token: string }>(r);
  return data.csrf_token;
}

export async function fetchMe(): Promise<UserPublic | null> {
  const r = await apiFetch("/api/v1/auth/me");
  if (r.status === 401) {
    return null;
  }
  if (!r.ok) {
    throw new Error(`me: ${r.status}`);
  }
  const data = await readJson<{ user: UserPublic }>(r);
  return data.user;
}

export async function fetchBootstrapStatus(): Promise<BootstrapStatus> {
  const r = await apiFetch("/api/v1/auth/bootstrap/status");
  if (!r.ok) {
    throw new Error(`bootstrap status: ${r.status}`);
  }
  return readJson<BootstrapStatus>(r);
}

export type LoginResult = { user: UserPublic };

export async function postLogin(username: string, password: string): Promise<LoginResult> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, csrf_token }),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await readJson<{ detail?: string | string[] }>(r);
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail || `login: ${r.status}`);
  }
  return readJson<LoginResult>(r);
}

export async function postLogout(): Promise<void> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/auth/logout", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
    },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok && r.status !== 204) {
    throw new Error(`logout: ${r.status}`);
  }
}

export async function postBootstrap(
  username: string,
  password: string,
): Promise<{ message: string; username: string }> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/auth/bootstrap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, csrf_token }),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await readJson<{ detail?: string }>(r);
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail || `bootstrap: ${r.status}`);
  }
  return readJson(r);
}
