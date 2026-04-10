import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson } from "../api/client";
import type { ManualCleanupDriveEnqueueOut } from "./types";

export const manualEnqueueRadarrCleanupDrivePath = () => "/api/v1/refiner/cleanup-drive/radarr/enqueue";

export const manualEnqueueSonarrCleanupDrivePath = () => "/api/v1/refiner/cleanup-drive/sonarr/enqueue";

async function postManualCleanupDriveEnqueue(path: string): Promise<ManualCleanupDriveEnqueueOut> {
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
    throw new Error(detail || `Could not queue cleanup drive (${r.status})`);
  }
  return readJson<ManualCleanupDriveEnqueueOut>(r);
}

export async function postManualEnqueueRadarrCleanupDrive(): Promise<ManualCleanupDriveEnqueueOut> {
  return postManualCleanupDriveEnqueue(manualEnqueueRadarrCleanupDrivePath());
}

export async function postManualEnqueueSonarrCleanupDrive(): Promise<ManualCleanupDriveEnqueueOut> {
  return postManualCleanupDriveEnqueue(manualEnqueueSonarrCleanupDrivePath());
}
