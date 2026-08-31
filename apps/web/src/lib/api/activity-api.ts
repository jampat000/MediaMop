import { apiFetch, readJson, requireOk } from "./client";
import type { ActivityRecentResponse } from "./types";

export type ActivityRecentFilters = {
  limit?: number;
  module?: string;
  event_type?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  before_id?: number;
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
  if (options?.before_id !== undefined)
    q.set("before_id", String(Math.trunc(options.before_id)));
  const qs = q.toString();
  return qs ? `/api/v1/activity/recent?${qs}` : "/api/v1/activity/recent";
}

export async function fetchActivityRecent(
  options?: ActivityRecentFilters,
): Promise<ActivityRecentResponse> {
  const path = activityRecentPath(options);
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load activity");
  return readJson<ActivityRecentResponse>(r);
}
