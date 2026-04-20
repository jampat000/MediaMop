import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  brokerSearch,
  createBrokerIndexer,
  deleteBrokerIndexer,
  getBrokerConnection,
  getBrokerIndexers,
  getBrokerJobs,
  getBrokerSettings,
  rotateBrokerProxyKey,
  syncBrokerConnection,
  testBrokerIndexer,
  updateBrokerConnection,
  updateBrokerIndexer,
  type BrokerIndexerCreateIn,
  type BrokerIndexerUpdateIn,
  type BrokerConnectionUpdateIn,
} from "./broker-api";

export function useBrokerIndexersQuery() {
  return useQuery({
    queryKey: ["broker", "indexers"],
    queryFn: getBrokerIndexers,
    staleTime: 10_000,
  });
}

export function useBrokerConnectionQuery(arrType: "sonarr" | "radarr") {
  return useQuery({
    queryKey: ["broker", "connection", arrType],
    queryFn: () => getBrokerConnection(arrType),
    staleTime: 10_000,
  });
}

export function useBrokerSettingsQuery() {
  return useQuery({
    queryKey: ["broker", "settings", "proxy"],
    queryFn: getBrokerSettings,
    staleTime: 15_000,
  });
}

export function useBrokerJobsQuery(opts: { enabled?: boolean; refetchIntervalMs?: number | false } = {}) {
  const { enabled = true, refetchIntervalMs = false } = opts;
  return useQuery({
    queryKey: ["broker", "jobs"],
    queryFn: getBrokerJobs,
    enabled,
    staleTime: 5_000,
    refetchInterval: refetchIntervalMs,
  });
}

export function useUpdateBrokerIndexerMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: BrokerIndexerUpdateIn }) => updateBrokerIndexer(id, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["broker", "indexers"] });
    },
  });
}

export function useCreateBrokerIndexerMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BrokerIndexerCreateIn) => createBrokerIndexer(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["broker", "indexers"] });
    },
  });
}

export function useDeleteBrokerIndexerMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteBrokerIndexer(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["broker", "indexers"] });
    },
  });
}

export function useTestBrokerIndexerMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => testBrokerIndexer(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["broker", "indexers"] });
    },
  });
}

export function useUpdateBrokerConnectionMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ arrType, data }: { arrType: "sonarr" | "radarr"; data: BrokerConnectionUpdateIn }) =>
      updateBrokerConnection(arrType, data),
    onSuccess: (_, { arrType }) => {
      void qc.invalidateQueries({ queryKey: ["broker", "connection", arrType] });
    },
  });
}

export function useBrokerManualSyncMutation(arrType: "sonarr" | "radarr") {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ["broker", "sync", arrType],
    mutationFn: () => syncBrokerConnection(arrType),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["broker", "connection", arrType] });
      void qc.invalidateQueries({ queryKey: ["broker", "jobs"] });
    },
  });
}

export function useRotateBrokerProxyKeyMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: rotateBrokerProxyKey,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["broker", "settings", "proxy"] });
    },
  });
}

export function useBrokerSearchMutation() {
  return useMutation({
    mutationFn: (params: { q: string; type?: string; indexers?: string; limit?: number }) => brokerSearch(params),
  });
}
