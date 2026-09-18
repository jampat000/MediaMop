import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchProcessingJobsInspection,
  postProcessingJobCancelPending,
  postProcessingJobRecoverFinalizeFailed,
} from "./api";

/** ``recent`` = no status filter — server returns newest rows across all statuses. */
export type ProcessingJobsInspectionFilter =
  | "recent"
  | "pending"
  | "leased"
  | "completed"
  | "failed"
  | "handler_ok_finalize_failed"
  | "cancelled"
  | "terminal";

export const processingJobsInspectionQueryKey = (
  filter: ProcessingJobsInspectionFilter,
  limit = 100,
) => ["processing", "jobs", "inspection", filter, limit] as const;

function statusesForFilter(
  filter: ProcessingJobsInspectionFilter,
): string[] | undefined {
  if (filter === "recent") {
    return undefined;
  }
  if (filter === "terminal") {
    return ["completed", "failed", "handler_ok_finalize_failed"];
  }
  return [filter];
}

export function useProcessingJobsInspectionQuery(
  filter: ProcessingJobsInspectionFilter,
  limit = 100,
) {
  return useQuery({
    queryKey: processingJobsInspectionQueryKey(filter, limit),
    queryFn: () =>
      fetchProcessingJobsInspection({
        limit,
        statuses: statusesForFilter(filter),
      }),
    staleTime: 15_000,
  });
}

export function useProcessingJobCancelPendingMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => postProcessingJobCancelPending(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["processing", "jobs", "inspection"],
      });
    },
  });
}

export function useProcessingJobRecoverFinalizeFailedMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) =>
      postProcessingJobRecoverFinalizeFailed(jobId),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["processing", "jobs", "inspection"],
      });
    },
  });
}
