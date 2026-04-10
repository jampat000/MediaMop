import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchRefinerJobsInspection } from "./refiner-inspection-api";
import {
  postManualEnqueueRadarrCleanupDrive,
  postManualEnqueueSonarrCleanupDrive,
} from "./refiner-manual-cleanup-enqueue-api";
import { fetchRefinerRuntimeVisibility } from "./refiner-runtime-visibility-api";
import { postRecoverFinalizeFailure } from "./refiner-recover-api";

/** ``terminal`` = omit status query param — server returns the three finished states only (completed, failed, handler_ok_finalize_failed). */
export type RefinerInspectionFilter = "terminal" | "pending" | "leased" | "completed" | "failed" | "handler_ok_finalize_failed";

export const refinerInspectionQueryKey = (filter: RefinerInspectionFilter) =>
  ["refiner", "jobs-inspection", filter] as const;

export const refinerRuntimeVisibilityQueryKey = ["refiner", "runtime-visibility"] as const;

export function useRefinerRuntimeVisibilityQuery() {
  return useQuery({
    queryKey: refinerRuntimeVisibilityQueryKey,
    queryFn: () => fetchRefinerRuntimeVisibility(),
    staleTime: 30_000,
  });
}

export function useRefinerJobsInspectionQuery(filter: RefinerInspectionFilter) {
  return useQuery({
    queryKey: refinerInspectionQueryKey(filter),
    queryFn: () =>
      fetchRefinerJobsInspection(
        filter === "terminal"
          ? { limit: 50 }
          : { limit: 50, statuses: [filter] },
      ),
    staleTime: 15_000,
  });
}

export function useRecoverFinalizeFailureMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => postRecoverFinalizeFailure(jobId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["refiner", "jobs-inspection"] });
    },
  });
}

export function useManualEnqueueRadarrCleanupDriveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postManualEnqueueRadarrCleanupDrive(),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["refiner", "jobs-inspection"] });
      void qc.invalidateQueries({ queryKey: ["refiner", "runtime-visibility"] });
    },
  });
}

export function useManualEnqueueSonarrCleanupDriveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postManualEnqueueSonarrCleanupDrive(),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["refiner", "jobs-inspection"] });
      void qc.invalidateQueries({ queryKey: ["refiner", "runtime-visibility"] });
    },
  });
}
