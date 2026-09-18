import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchDirectPlayDevices,
  putDirectPlayDevices,
} from "./direct-play-api";

const directPlayDevicesQueryKey = [
  "processing",
  "direct-play-devices",
] as const;

export function useDirectPlayDevicesQuery() {
  return useQuery({
    queryKey: directPlayDevicesQueryKey,
    queryFn: () => fetchDirectPlayDevices(),
    staleTime: 30_000,
  });
}

export function useDirectPlayDevicesSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (selected: string[]) => putDirectPlayDevices(selected),
    onSuccess: (data) => {
      qc.setQueryData(directPlayDevicesQueryKey, data);
      // The badge on every file row answers for the chosen devices.
      void qc.invalidateQueries({ queryKey: ["processing", "files"] });
    },
  });
}
