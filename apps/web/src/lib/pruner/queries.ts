import { useQuery } from "@tanstack/react-query";
import { fetchPrunerInstance, fetchPrunerInstances, fetchPrunerJobsInspection } from "./api";

export function usePrunerInstancesQuery() {
  return useQuery({
    queryKey: ["pruner", "instances"],
    queryFn: fetchPrunerInstances,
  });
}

export function usePrunerInstanceQuery(instanceId: number) {
  return useQuery({
    queryKey: ["pruner", "instances", instanceId],
    queryFn: () => fetchPrunerInstance(instanceId),
    enabled: Number.isFinite(instanceId) && instanceId > 0,
  });
}

export function usePrunerJobsInspectionQuery(limit = 50) {
  return useQuery({
    queryKey: ["pruner", "jobs-inspection", limit],
    queryFn: () => fetchPrunerJobsInspection(limit),
  });
}
