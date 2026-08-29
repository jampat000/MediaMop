import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export type MaintenanceFamily = "work_temp_stale_sweep" | "failure_cleanup";

export interface MaintenanceFamilyState {
  family: MaintenanceFamily;
  /** Whether the schedule runs this. Triggering by hand ignores it. */
  enabled: boolean;
  description: string;
  pending: number;
  running: number;
  last_completed_at: string | null;
  last_failed_at: string | null;
  last_error: string | null;
}

export interface MaintenanceState {
  families: MaintenanceFamilyState[];
}

export interface MaintenanceTriggerResult {
  queued: boolean;
  detail: string;
  job_id: number | null;
}

export const refinerMaintenancePath = () => "/api/v1/refiner/maintenance";

export async function fetchRefinerMaintenance(): Promise<MaintenanceState> {
  const path = refinerMaintenancePath();
  const response = await apiFetch(path);
  await requireOk(path, response, "Could not read the maintenance state");
  return readJson<MaintenanceState>(response);
}

export async function runRefinerMaintenance(
  family: MaintenanceFamily,
  media_scope: "movie" | "tv",
): Promise<MaintenanceTriggerResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerMaintenancePath()}/run`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token, family, media_scope }),
  });
  await requireOk(path, response, "Could not start that maintenance job");
  return readJson<MaintenanceTriggerResult>(response);
}
