import { useQuery } from "@tanstack/react-query";
import {
  fetchActivityRecent,
  type ActivityRecentFilters,
} from "../api/activity-api";

export const activityRecentKey = ["activity", "recent"] as const;

export function useActivityRecentQuery(filters?: ActivityRecentFilters) {
  return useQuery({
    queryKey: [...activityRecentKey, filters ?? {}],
    queryFn: () => fetchActivityRecent(filters),
    staleTime: 15_000,
  });
}

/** Narrower feed for Settings → Logs (does not share cache with open-ended ``/recent``). */
export const activityRecentSettingsKey = [
  "activity",
  "recent",
  "settings",
  20,
] as const;

export function useActivityRecentForSettingsQuery(enabled: boolean) {
  return useQuery({
    queryKey: activityRecentSettingsKey,
    queryFn: () => fetchActivityRecent({ limit: 20 }),
    staleTime: 15_000,
    enabled,
  });
}
