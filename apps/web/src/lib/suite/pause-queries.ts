import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchSuitePause,
  saveSuitePause,
  type SuitePause,
  type SuitePauseWrite,
} from "./pause-api";

export const suitePauseKey = () => ["suite", "pause"];

export function useSuitePauseQuery() {
  return useQuery<SuitePause>({
    queryKey: suitePauseKey(),
    queryFn: fetchSuitePause,
    // A pause with an expiry lifts on its own, so the shell has to notice without a
    // reload. One minute is well inside the smallest pause anyone can set.
    refetchInterval: 60_000,
  });
}

export function useSaveSuitePause() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SuitePauseWrite) => saveSuitePause(body),
    onSuccess: (data) => {
      qc.setQueryData(suitePauseKey(), data);
      // Pausing changes why files are in the state they are in, so the Files screen is
      // stale the moment this succeeds.
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] });
    },
  });
}
