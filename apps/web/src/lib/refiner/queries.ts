import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { postRefinerFileRemuxPassEnqueue } from "./file-remux-pass-api";
import { fetchRefinerOperatorSettings, putRefinerOperatorSettings } from "./operator-settings-api";
import { fetchRefinerOverviewStats } from "./overview-stats-api";
import { fetchRefinerPathSettings, putRefinerPathSettings } from "./path-settings-api";
import { fetchRefinerRemuxRulesSettings, putRefinerRemuxRulesSettings } from "./remux-rules-settings-api";
import { fetchRefinerRuntimeSettings } from "./runtime-settings-api";
import { postRefinerWatchedFolderRemuxScanDispatchEnqueue } from "./watched-folder-scan-api";
import type {
  RefinerFileRemuxPassManualEnqueueBody,
  RefinerOperatorSettingsPutBody,
  RefinerPathSettingsPutBody,
  RefinerRemuxRulesSettingsPutBody,
  RefinerWatchedFolderRemuxScanDispatchEnqueueBody,
} from "./types";

export const refinerPathSettingsQueryKey = ["refiner", "path-settings"] as const;
export const refinerOverviewStatsQueryKey = ["refiner", "overview-stats"] as const;
export const refinerOperatorSettingsQueryKey = ["refiner", "operator-settings"] as const;

export function useRefinerOverviewStatsQuery() {
  return useQuery({
    queryKey: refinerOverviewStatsQueryKey,
    queryFn: () => fetchRefinerOverviewStats(),
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
    mutationFn: (body: RefinerOperatorSettingsPutBody) => putRefinerOperatorSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(refinerOperatorSettingsQueryKey, data);
      void qc.invalidateQueries({ queryKey: refinerRuntimeSettingsQueryKey });
    },
  });
}

export function useRefinerPathSettingsQuery() {
  return useQuery({
    queryKey: refinerPathSettingsQueryKey,
    queryFn: () => fetchRefinerPathSettings(),
    staleTime: 30_000,
  });
}

export function useRefinerPathSettingsSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RefinerPathSettingsPutBody) => putRefinerPathSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(refinerPathSettingsQueryKey, data);
    },
  });
}

export const refinerRuntimeSettingsQueryKey = ["refiner", "runtime-settings"] as const;

export function useRefinerRuntimeSettingsQuery() {
  return useQuery({
    queryKey: refinerRuntimeSettingsQueryKey,
    queryFn: () => fetchRefinerRuntimeSettings(),
    staleTime: 30_000,
  });
}

export function useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation() {
  return useMutation({
    mutationFn: (body: RefinerWatchedFolderRemuxScanDispatchEnqueueBody) =>
      postRefinerWatchedFolderRemuxScanDispatchEnqueue(body),
  });
}

export const refinerRemuxRulesSettingsQueryKey = ["refiner", "remux-rules-settings"] as const;

export function useRefinerRemuxRulesSettingsQuery() {
  return useQuery({
    queryKey: refinerRemuxRulesSettingsQueryKey,
    queryFn: () => fetchRefinerRemuxRulesSettings(),
    staleTime: 30_000,
  });
}

export function useRefinerRemuxRulesSettingsSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RefinerRemuxRulesSettingsPutBody) => putRefinerRemuxRulesSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(refinerRemuxRulesSettingsQueryKey, data);
    },
  });
}

export function useRefinerFileRemuxPassEnqueueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RefinerFileRemuxPassManualEnqueueBody) => postRefinerFileRemuxPassEnqueue(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["refiner", "jobs", "inspection"] });
    },
  });
}
