import { apiFetch, readJson, requireOk } from "../api/client";
import type { RefinerRuntimeSettingsOut } from "./types";

export const refinerRuntimeSettingsPath = () =>
  "/api/v1/refiner/runtime-settings";

export async function fetchRefinerRuntimeSettings(): Promise<RefinerRuntimeSettingsOut> {
  const path = refinerRuntimeSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner runtime settings");
  return readJson<RefinerRuntimeSettingsOut>(r);
}
