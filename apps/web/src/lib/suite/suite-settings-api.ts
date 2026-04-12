import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson } from "../api/client";
import type { SuiteSecurityOverviewOut, SuiteSettingsOut, SuiteSettingsPutBody } from "./types";

export const suiteSettingsPath = () => "/api/v1/suite/settings";
export const suiteSecurityOverviewPath = () => "/api/v1/suite/security-overview";

export async function fetchSuiteSettings(): Promise<SuiteSettingsOut> {
  const r = await apiFetch(suiteSettingsPath());
  if (!r.ok) {
    throw new Error(`Could not load suite settings (${r.status})`);
  }
  return readJson<SuiteSettingsOut>(r);
}

export async function putSuiteSettings(body: SuiteSettingsPutBody): Promise<SuiteSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(suiteSettingsPath(), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const b = await readJson<{ detail?: string }>(r);
      if (typeof b.detail === "string") {
        detail = b.detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Could not save suite settings (${r.status})`);
  }
  return readJson<SuiteSettingsOut>(r);
}

export async function fetchSuiteSecurityOverview(): Promise<SuiteSecurityOverviewOut> {
  const r = await apiFetch(suiteSecurityOverviewPath());
  if (!r.ok) {
    throw new Error(`Could not load security overview (${r.status})`);
  }
  return readJson<SuiteSecurityOverviewOut>(r);
}
