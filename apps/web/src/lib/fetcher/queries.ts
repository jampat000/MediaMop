import { useQuery } from "@tanstack/react-query";
import { fetchFetcherOverviewStats } from "./overview-stats-api";

export const fetcherOverviewStatsQueryKey = ["fetcher", "overview-stats"] as const;

export function useFetcherOverviewStatsQuery() {
  return useQuery({
    queryKey: fetcherOverviewStatsQueryKey,
    queryFn: () => fetchFetcherOverviewStats(),
    staleTime: 30_000,
  });
}
