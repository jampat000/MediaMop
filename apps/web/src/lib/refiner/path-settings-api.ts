import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson } from "../api/client";
import type { RefinerPathSettingsOut, RefinerPathSettingsPutBody } from "./types";

export const refinerPathSettingsPath = () => "/api/v1/refiner/path-settings";

export async function fetchRefinerPathSettings(): Promise<RefinerPathSettingsOut> {
  const r = await apiFetch(refinerPathSettingsPath());
  if (!r.ok) {
    throw new Error(`Could not load Refiner path settings (${r.status})`);
  }
  return readJson<RefinerPathSettingsOut>(r);
}

export async function putRefinerPathSettings(body: RefinerPathSettingsPutBody): Promise<RefinerPathSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(refinerPathSettingsPath(), {
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
    throw new Error(detail || `Could not save Refiner path settings (${r.status})`);
  }
  return readJson<RefinerPathSettingsOut>(r);
}
