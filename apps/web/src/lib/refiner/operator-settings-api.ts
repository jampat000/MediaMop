import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson } from "../api/client";
import type { RefinerOperatorSettingsOut, RefinerOperatorSettingsPutBody } from "./types";

export const refinerOperatorSettingsPath = () => "/api/v1/refiner/operator-settings";

export async function fetchRefinerOperatorSettings(): Promise<RefinerOperatorSettingsOut> {
  const r = await apiFetch(refinerOperatorSettingsPath());
  if (!r.ok) {
    throw new Error(`Could not load Refiner automation settings (${r.status})`);
  }
  return readJson<RefinerOperatorSettingsOut>(r);
}

export async function putRefinerOperatorSettings(
  body: RefinerOperatorSettingsPutBody,
): Promise<RefinerOperatorSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(refinerOperatorSettingsPath(), {
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
    throw new Error(detail || `Could not save Refiner automation settings (${r.status})`);
  }
  return readJson<RefinerOperatorSettingsOut>(r);
}
