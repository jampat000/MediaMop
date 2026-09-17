import { useQuery } from "@tanstack/react-query";

import { fetchSystemReadiness } from "./readiness-api";

const systemReadinessKey = ["system", "readiness"] as const;

export function useSystemReadinessQuery() {
  return useQuery({
    queryKey: systemReadinessKey,
    queryFn: fetchSystemReadiness,
    staleTime: 30_000,
    // Workers can stop while the screen is open, and the shell shows the version.
    refetchInterval: 60_000,
  });
}
