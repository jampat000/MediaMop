import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchProcessingOperatorSettings,
  putProcessingOperatorSettings,
} from "./operator-settings-api";
import { fetchProcessingOverviewStats } from "./overview-stats-api";
import { postProcessingWatchedFolderRemuxScanDispatchEnqueue } from "./watched-folder-scan-api";
import type {
  ProcessingOperatorSettingsPutBody,
  ProcessingWatchedFolderRemuxScanDispatchEnqueueBody,
} from "./types";

export const processingOverviewStatsQueryKey = [
  "processing",
  "overview-stats",
] as const;
export const processingOperatorSettingsQueryKey = [
  "processing",
  "operator-settings",
] as const;

export function useProcessingOverviewStatsQuery(windowDays?: number) {
  return useQuery({
    queryKey:
      windowDays === undefined
        ? processingOverviewStatsQueryKey
        : [...processingOverviewStatsQueryKey, windowDays],
    queryFn: () => fetchProcessingOverviewStats(windowDays),
    staleTime: 30_000,
  });
}

export function useProcessingOperatorSettingsQuery() {
  return useQuery({
    queryKey: processingOperatorSettingsQueryKey,
    queryFn: () => fetchProcessingOperatorSettings(),
    staleTime: 30_000,
  });
}

export function useProcessingOperatorSettingsSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProcessingOperatorSettingsPutBody) =>
      putProcessingOperatorSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(processingOperatorSettingsQueryKey, data);
      void qc.invalidateQueries({
        queryKey: processingRuntimeSettingsQueryKey,
      });
    },
  });
}

export const processingRuntimeSettingsQueryKey = [
  "processing",
  "runtime-settings",
] as const;

export function useProcessingWatchedFolderRemuxScanDispatchEnqueueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProcessingWatchedFolderRemuxScanDispatchEnqueueBody) =>
      postProcessingWatchedFolderRemuxScanDispatchEnqueue(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["processing", "files"] });
      void qc.invalidateQueries({ queryKey: ["processing", "jobs"] });
    },
  });
}
