import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchRefinerPathSettings, putRefinerPathSettings } from "./path-settings-api";
import { fetchRefinerRuntimeSettings } from "./runtime-settings-api";
import type { RefinerPathSettingsPutBody } from "./types";

export const refinerPathSettingsQueryKey = ["refiner", "path-settings"] as const;

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
