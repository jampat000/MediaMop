import { apiFetch, readJson } from "../../api/client";
import type { FailedImportFetcherSettingsOut } from "./types";

export const failedImportFetcherSettingsPath = () => "/api/v1/fetcher/failed-imports/settings";

export async function fetchFailedImportFetcherSettings(): Promise<FailedImportFetcherSettingsOut> {
  const r = await apiFetch(failedImportFetcherSettingsPath());
  if (!r.ok) {
    throw new Error(`Could not load Fetcher failed-import settings (${r.status})`);
  }
  return readJson<FailedImportFetcherSettingsOut>(r);
}
