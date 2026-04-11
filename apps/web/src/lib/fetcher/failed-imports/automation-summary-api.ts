import { apiFetch, readJson } from "../../api/client";
import type { FetcherFailedImportAutomationSummary } from "./types";

export const failedImportAutomationSummaryPath = () => "/api/v1/fetcher/failed-imports/automation-summary";

export async function fetchFailedImportAutomationSummary(): Promise<FetcherFailedImportAutomationSummary> {
  const r = await apiFetch(failedImportAutomationSummaryPath());
  if (!r.ok) {
    throw new Error(`Could not load Fetcher automation summary (${r.status})`);
  }
  return readJson<FetcherFailedImportAutomationSummary>(r);
}
