import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchPause,
  savePause,
  type PauseState,
  type PauseWrite,
} from "./pause-api";

export const pauseKey = () => ["pause"];

export function usePauseQuery() {
  return useQuery<PauseState>({
    queryKey: pauseKey(),
    queryFn: fetchPause,
    // A pause with an expiry lifts on its own, so the shell has to notice without a
    // reload. One minute is well inside the smallest pause anyone can set.
    refetchInterval: 60_000,
  });
}

export function useSavePause() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PauseWrite) => savePause(body),
    onSuccess: (data) => {
      qc.setQueryData(pauseKey(), data);
      // Pausing changes why files are in the state they are in, so the Files screen is
      // stale the moment this succeeds.
      void qc.invalidateQueries({ queryKey: ["processing", "files"] });
    },
  });
}
