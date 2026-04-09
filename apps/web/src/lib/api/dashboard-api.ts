import { apiFetch, readJson } from "./client";
import type { DashboardStatus } from "./types";

export async function fetchDashboardStatus(): Promise<DashboardStatus> {
  const r = await apiFetch("/api/v1/dashboard/status");
  if (!r.ok) {
    throw new Error(`dashboard status: ${r.status}`);
  }
  return readJson<DashboardStatus>(r);
}
