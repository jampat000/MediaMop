import { apiFetch, readJson } from "./client";
import type { ActivityRecentResponse } from "./types";

export type ActivityRecentFilters = {
  limit?: number;
  module?: string;
  event_type?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
};

export function activityRecentPath(options?: ActivityRecentFilters): string {
  const q = new URLSearchParams();
  const lim = options?.limit;
  if (lim !== undefined && Number.isFinite(lim)) {
    q.set("limit", String(Math.trunc(lim)));
  }
  if (options?.module) q.set("module", options.module);
  if (options?.event_type) q.set("event_type", options.event_type);
  if (options?.search) q.set("search", options.search);
  if (options?.date_from) q.set("date_from", options.date_from);
  if (options?.date_to) q.set("date_to", options.date_to);
  const qs = q.toString();
  return qs ? `/api/v1/activity/recent?${qs}` : "/api/v1/activity/recent";
}

export async function fetchActivityRecent(options?: ActivityRecentFilters): Promise<ActivityRecentResponse> {
  const r = await apiFetch(activityRecentPath(options));
  if (!r.ok) {
    throw new Error(`activity recent: ${r.status}`);
  }
  return readJson<ActivityRecentResponse>(r);
}
