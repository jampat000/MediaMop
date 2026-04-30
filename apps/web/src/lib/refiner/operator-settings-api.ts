import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type {
  RefinerOperatorSettingsOut,
  RefinerOperatorSettingsPutBody,
} from "./types";

export const refinerOperatorSettingsPath = () =>
  "/api/v1/refiner/operator-settings";

export async function fetchRefinerOperatorSettings(): Promise<RefinerOperatorSettingsOut> {
  const path = refinerOperatorSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner automation settings");
  return readJson<RefinerOperatorSettingsOut>(r);
}

export async function putRefinerOperatorSettings(
  body: RefinerOperatorSettingsPutBody,
): Promise<RefinerOperatorSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const path = refinerOperatorSettingsPath();
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not save Refiner automation settings");
  return readJson<RefinerOperatorSettingsOut>(r);
}
