import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchRefinerJobsInspection,
  postRefinerJobCancelPending,
  postRefinerJobRecoverFinalizeFailed,
} from "./api";

/** ``recent`` = no status filter — server returns newest rows across all statuses. */
export type RefinerJobsInspectionFilter =
  | "recent"
  | "pending"
  | "leased"
  | "completed"
  | "failed"
  | "handler_ok_finalize_failed"
  | "cancelled"
  | "terminal";

export const refinerJobsInspectionQueryKey = (
  filter: RefinerJobsInspectionFilter,
  limit = 100,
) => ["refiner", "jobs", "inspection", filter, limit] as const;

function statusesForFilter(
  filter: RefinerJobsInspectionFilter,
): string[] | undefined {
  if (filter === "recent") {
    return undefined;
  }
  if (filter === "terminal") {
    return ["completed", "failed", "handler_ok_finalize_failed"];
  }
  return [filter];
}

export function useRefinerJobsInspectionQuery(
  filter: RefinerJobsInspectionFilter,
  limit = 100,
) {
  return useQuery({
    queryKey: refinerJobsInspectionQueryKey(filter, limit),
    queryFn: () =>
      fetchRefinerJobsInspection({
        limit,
        statuses: statusesForFilter(filter),
      }),
    staleTime: 15_000,
  });
}

export function useRefinerJobCancelPendingMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => postRefinerJobCancelPending(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["refiner", "jobs", "inspection"],
      });
    },
  });
}

export function useRefinerJobRecoverFinalizeFailedMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => postRefinerJobRecoverFinalizeFailed(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["refiner", "jobs", "inspection"],
      });
    },
  });
}
