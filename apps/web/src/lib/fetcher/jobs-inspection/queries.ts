import { useQuery } from "@tanstack/react-query";
import { fetchFetcherJobsInspection } from "./api";

/** terminal = omit status param — server returns completed, failed, handler_ok_finalize_failed only. */
export type FetcherJobsInspectionFilter =
  | "terminal"
  | "pending"
  | "leased"
  | "completed"
  | "failed"
  | "handler_ok_finalize_failed";

export const fetcherJobsInspectionQueryKey = (filter: FetcherJobsInspectionFilter) =>
  ["fetcher", "jobs", "inspection", filter] as const;

export function useFetcherJobsInspectionQuery(filter: FetcherJobsInspectionFilter) {
  return useQuery({
    queryKey: fetcherJobsInspectionQueryKey(filter),
    queryFn: () =>
      fetchFetcherJobsInspection(
        filter === "terminal" ? { limit: 50 } : { limit: 50, statuses: [filter] },
      ),
    staleTime: 15_000,
  });
}
