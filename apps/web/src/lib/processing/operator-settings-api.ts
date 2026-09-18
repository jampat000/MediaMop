import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type {
  ProcessingOperatorSettingsOut,
  ProcessingOperatorSettingsPutBody,
} from "./types";

export const processingOperatorSettingsPath = () =>
  "/api/v1/processing/operator-settings";

export async function fetchProcessingOperatorSettings(): Promise<ProcessingOperatorSettingsOut> {
  const path = processingOperatorSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load processing settings");
  return readJson<ProcessingOperatorSettingsOut>(r);
}

export async function putProcessingOperatorSettings(
  body: ProcessingOperatorSettingsPutBody,
): Promise<ProcessingOperatorSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const path = processingOperatorSettingsPath();
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not save processing settings");
  return readJson<ProcessingOperatorSettingsOut>(r);
}
