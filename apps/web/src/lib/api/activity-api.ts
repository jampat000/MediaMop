import { apiFetch, readJson } from "./client";
import type { ActivityRecentResponse } from "./types";

export function activityRecentPath(options?: { limit?: number }): string {
  const lim = options?.limit;
  if (lim !== undefined && Number.isFinite(lim)) {
    const q = new URLSearchParams({ limit: String(Math.trunc(lim)) });
    return `/api/v1/activity/recent?${q.toString()}`;
  }
  return "/api/v1/activity/recent";
}

export async function fetchActivityRecent(options?: { limit?: number }): Promise<ActivityRecentResponse> {
  const r = await apiFetch(activityRecentPath(options));
  if (!r.ok) {
    throw new Error(`activity recent: ${r.status}`);
  }
  return readJson<ActivityRecentResponse>(r);
}
