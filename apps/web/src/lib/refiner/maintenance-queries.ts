import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchRefinerMaintenance,
  runRefinerMaintenance,
  type MaintenanceFamily,
  type MaintenanceState,
} from "./maintenance-api";
import { fetchRefinerRuntimeSettings } from "./runtime-settings-api";
import type { RefinerRuntimeSettingsOut } from "./types";

export const refinerMaintenanceKey = () => ["refiner", "maintenance"];

export function useRefinerMaintenanceQuery() {
  return useQuery<MaintenanceState>({
    queryKey: refinerMaintenanceKey(),
    queryFn: fetchRefinerMaintenance,
    // A queued sweep starts within seconds, so the panel has to notice without a reload.
    refetchInterval: 15_000,
  });
}

export function useRunRefinerMaintenance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      family,
      mediaScope,
    }: {
      family: MaintenanceFamily;
      mediaScope: "movie" | "tv";
    }) => runRefinerMaintenance(family, mediaScope),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerMaintenanceKey() }),
  });
}

export const refinerRuntimeSettingsKey = () => ["refiner", "runtime-settings"];

export function useRefinerRuntimeSettingsQuery() {
  return useQuery<RefinerRuntimeSettingsOut>({
    queryKey: refinerRuntimeSettingsKey(),
    queryFn: fetchRefinerRuntimeSettings,
  });
}
