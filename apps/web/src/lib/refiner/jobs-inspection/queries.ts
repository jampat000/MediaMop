import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchRefinerJobsInspection, postRefinerJobCancelPending } from "./api";

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
) => ["refiner", "jobs", "inspection", filter] as const;

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
) {
  return useQuery({
    queryKey: refinerJobsInspectionQueryKey(filter),
    queryFn: () =>
      fetchRefinerJobsInspection({
        limit: 100,
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
