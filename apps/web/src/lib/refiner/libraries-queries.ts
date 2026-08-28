import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createRefinerLibrary,
  deleteRefinerLibrary,
  fetchRefinerLibraries,
  reorderRefinerLibraries,
  updateRefinerLibrary,
  type RefinerLibrary,
  type RefinerLibraryWrite,
} from "./libraries-api";

export const refinerLibrariesKey = ["refiner", "libraries"];

export function useRefinerLibrariesQuery(enabled = true) {
  return useQuery<RefinerLibrary[]>({
    queryKey: refinerLibrariesKey,
    queryFn: fetchRefinerLibraries,
    enabled,
  });
}

export function useCreateRefinerLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RefinerLibraryWrite) => createRefinerLibrary(data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerLibrariesKey }),
  });
}

export function useUpdateRefinerLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; data: RefinerLibraryWrite }) =>
      updateRefinerLibrary(vars.id, vars.data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerLibrariesKey }),
  });
}

export function useDeleteRefinerLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRefinerLibrary(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerLibrariesKey }),
  });
}

export function useReorderRefinerLibraries() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) => reorderRefinerLibraries(ids),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerLibrariesKey }),
  });
}
