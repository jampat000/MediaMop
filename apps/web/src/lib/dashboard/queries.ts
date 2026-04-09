import { useQuery } from "@tanstack/react-query";
import { fetchDashboardStatus } from "../api/dashboard-api";

export const dashboardStatusKey = ["dashboard", "status"] as const;

export function useDashboardStatusQuery() {
  return useQuery({
    queryKey: dashboardStatusKey,
    queryFn: fetchDashboardStatus,
    staleTime: 30_000,
  });
}
