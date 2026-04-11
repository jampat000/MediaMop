import { fetchCsrfToken } from "../../api/auth-api";
import { apiFetch, readJson } from "../../api/client";
import type { FailedImportManualQueuePassOut } from "./types";

export const failedImportRadarrEnqueuePath = () => "/api/v1/fetcher/failed-imports/radarr/enqueue";

export const failedImportSonarrEnqueuePath = () => "/api/v1/fetcher/failed-imports/sonarr/enqueue";

async function postFailedImportEnqueue(path: string): Promise<FailedImportManualQueuePassOut> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, csrf_token }),
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
    throw new Error(detail || `Could not queue failed-import pass (${r.status})`);
  }
  return readJson<FailedImportManualQueuePassOut>(r);
}

export async function postFailedImportRadarrEnqueue(): Promise<FailedImportManualQueuePassOut> {
  return postFailedImportEnqueue(failedImportRadarrEnqueuePath());
}

export async function postFailedImportSonarrEnqueue(): Promise<FailedImportManualQueuePassOut> {
  return postFailedImportEnqueue(failedImportSonarrEnqueuePath());
}
