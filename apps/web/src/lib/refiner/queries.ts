import { useQuery } from "@tanstack/react-query";
import { fetchRefinerJobsInspection } from "./refiner-inspection-api";

/** ``terminal`` = no ``status`` query param — server returns completed, failed, handler_ok_finalize_failed only. */
export type RefinerInspectionFilter = "terminal" | "pending" | "leased" | "completed" | "failed" | "handler_ok_finalize_failed";

export const refinerInspectionQueryKey = (filter: RefinerInspectionFilter) =>
  ["refiner", "jobs-inspection", filter] as const;

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
