import { apiFetch, readJson, requireOk } from "../api/client";
import type { RefinerRemuxRulesSettingsOut } from "./types";

export const refinerRemuxRulesSettingsPath = () =>
  "/api/v1/refiner/remux-rules-settings";

export async function fetchRefinerRemuxRulesSettings(): Promise<RefinerRemuxRulesSettingsOut> {
  const path = refinerRemuxRulesSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load remux defaults");
  return readJson<RefinerRemuxRulesSettingsOut>(r);
}
