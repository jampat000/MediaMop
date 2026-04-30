import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type {
  RefinerRemuxRulesSettingsOut,
  RefinerRemuxRulesSettingsPutBody,
} from "./types";

export const refinerRemuxRulesSettingsPath = () =>
  "/api/v1/refiner/remux-rules-settings";

export async function fetchRefinerRemuxRulesSettings(): Promise<RefinerRemuxRulesSettingsOut> {
  const path = refinerRemuxRulesSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load remux defaults");
  return readJson<RefinerRemuxRulesSettingsOut>(r);
}

export async function putRefinerRemuxRulesSettings(
  body: RefinerRemuxRulesSettingsPutBody,
): Promise<RefinerRemuxRulesSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const path = refinerRemuxRulesSettingsPath();
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not save remux defaults");
  return readJson<RefinerRemuxRulesSettingsOut>(r);
}
