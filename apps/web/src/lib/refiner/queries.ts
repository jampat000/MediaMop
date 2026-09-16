import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchRefinerOperatorSettings,
  putRefinerOperatorSettings,
} from "./operator-settings-api";
import { fetchRefinerOverviewStats } from "./overview-stats-api";
import { postRefinerWatchedFolderRemuxScanDispatchEnqueue } from "./watched-folder-scan-api";
import type {
  RefinerOperatorSettingsPutBody,
  RefinerWatchedFolderRemuxScanDispatchEnqueueBody,
} from "./types";

export const refinerOverviewStatsQueryKey = [
  "refiner",
  "overview-stats",
] as const;
export const refinerOperatorSettingsQueryKey = [
  "refiner",
  "operator-settings",
] as const;

export function useRefinerOverviewStatsQuery(windowDays?: number) {
  return useQuery({
    queryKey:
      windowDays === undefined
        ? refinerOverviewStatsQueryKey
        : [...refinerOverviewStatsQueryKey, windowDays],
    queryFn: () => fetchRefinerOverviewStats(windowDays),
    staleTime: 30_000,
  });
}

export function useRefinerOperatorSettingsQuery() {
  return useQuery({
    queryKey: refinerOperatorSettingsQueryKey,
    queryFn: () => fetchRefinerOperatorSettings(),
    staleTime: 30_000,
  });
}

export function useRefinerOperatorSettingsSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RefinerOperatorSettingsPutBody) =>
      putRefinerOperatorSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(refinerOperatorSettingsQueryKey, data);
      void qc.invalidateQueries({ queryKey: refinerRuntimeSettingsQueryKey });
    },
  });
}

export const refinerRuntimeSettingsQueryKey = [
  "refiner",
  "runtime-settings",
] as const;

export function useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RefinerWatchedFolderRemuxScanDispatchEnqueueBody) =>
      postRefinerWatchedFolderRemuxScanDispatchEnqueue(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] });
      void qc.invalidateQueries({ queryKey: ["refiner", "jobs"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
