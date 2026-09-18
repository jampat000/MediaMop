import { apiFetch, readJson, requireOk } from "../api/client";
import type { ProcessingRuntimeSettingsOut } from "./types";

export const processingRuntimeSettingsPath = () =>
  "/api/v1/processing/runtime-settings";

export async function fetchProcessingRuntimeSettings(): Promise<ProcessingRuntimeSettingsOut> {
  const path = processingRuntimeSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load runtime settings");
  return readJson<ProcessingRuntimeSettingsOut>(r);
}
