import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createRefinerLibrary,
  createRefinerRuleSet,
  deleteRefinerLibrary,
  deleteRefinerRuleSet,
  discoverRefinerLibraries,
  fetchRefinerLibraryDrift,
  fetchRefinerLibraries,
  fetchRefinerRuleSets,
  importDiscoveredRefinerLibraries,
  reorderRefinerLibraries,
  unlinkDiscoveredRefinerLibrary,
  updateRefinerLibrary,
  updateRefinerRuleSet,
  type RefinerLibrary,
  type RefinerLibraryWrite,
  type RefinerRuleSet,
  type RefinerRuleSetWrite,
} from "./libraries-api";

export const refinerLibrariesKey = ["refiner", "libraries"];
export const refinerRuleSetsKey = ["refiner", "rule-sets"];

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

export function useDiscoverRefinerLibraries() {
  return useMutation({
    mutationFn: (connectionId: number) =>
      discoverRefinerLibraries(connectionId),
  });
}

export function useImportDiscoveredRefinerLibraries() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { connectionId: number; keys: string[] }) =>
      importDiscoveredRefinerLibraries(vars.connectionId, vars.keys),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerLibrariesKey }),
  });
}

export function useRefinerLibraryDrift() {
  return useMutation({
    mutationFn: (connectionId: number) =>
      fetchRefinerLibraryDrift(connectionId),
  });
}

export function useUnlinkDiscoveredRefinerLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unlinkDiscoveredRefinerLibrary(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerLibrariesKey }),
  });
}

export function useRefinerRuleSetsQuery() {
  return useQuery<RefinerRuleSet[]>({
    queryKey: refinerRuleSetsKey,
    queryFn: fetchRefinerRuleSets,
  });
}

export function useCreateRefinerRuleSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RefinerRuleSetWrite) => createRefinerRuleSet(data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerRuleSetsKey }),
  });
}

export function useUpdateRefinerRuleSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; data: RefinerRuleSetWrite }) =>
      updateRefinerRuleSet(vars.id, vars.data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: refinerRuleSetsKey }),
  });
}

export function useDeleteRefinerRuleSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRefinerRuleSet(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: refinerRuleSetsKey });
      void qc.invalidateQueries({ queryKey: refinerLibrariesKey });
    },
  });
}
