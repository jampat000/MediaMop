import { apiFetch, readJson, requireOk } from "./client";
import type { DashboardStatus } from "./types";

export async function fetchDashboardStatus(): Promise<DashboardStatus> {
  const path = "/api/v1/dashboard/status";
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load dashboard status");
  return readJson<DashboardStatus>(r);
}
