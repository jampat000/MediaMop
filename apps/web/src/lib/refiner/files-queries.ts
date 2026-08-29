import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchRefinerFiles,
  forgetRefinerFile,
  moveRefinerFileToTop,
  type RefinerFilesPage,
  type RefinerFilesQuery,
} from "./files-api";

export const refinerFilesKey = (query: RefinerFilesQuery) => [
  "refiner",
  "files",
  query,
];

export function useRefinerFilesQuery(query: RefinerFilesQuery = {}) {
  return useQuery<RefinerFilesPage>({
    queryKey: refinerFilesKey(query),
    queryFn: () => fetchRefinerFiles(query),
  });
}

export function useForgetRefinerFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => forgetRefinerFile(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] }),
  });
}

export function useMoveRefinerFileToTop() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => moveRefinerFileToTop(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] }),
  });
}
