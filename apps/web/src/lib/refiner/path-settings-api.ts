import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type { RefinerPathSettingsOut, RefinerPathSettingsPutBody } from "./types";

export const refinerPathSettingsPath = () => "/api/v1/refiner/path-settings";

export async function fetchRefinerPathSettings(): Promise<RefinerPathSettingsOut> {
  const path = refinerPathSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner path settings");
  return readJson<RefinerPathSettingsOut>(r);
}

export async function putRefinerPathSettings(body: RefinerPathSettingsPutBody): Promise<RefinerPathSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const path = refinerPathSettingsPath();
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not save Refiner path settings");
  return readJson<RefinerPathSettingsOut>(r);
}
