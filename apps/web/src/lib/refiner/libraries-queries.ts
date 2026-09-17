import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createRefinerLibrary,
  createRefinerRuleSet,
  deleteRefinerLibrary,
  deleteRefinerRuleSet,
  discoverRefinerLibraries,
  fetchRefinerLibraryDrift,
  fetchRefinerRejectSupport,
  fetchRefinerLibraries,
  fetchRefinerRuleSets,
  importDiscoveredRefinerLibraries,
  reorderRefinerLibraries,
  unlinkDiscoveredRefinerLibrary,
  updateRefinerLibrary,
  updateRefinerRuleSet,
  type RefinerLibrary,
  type RefinerLibraryCreate,
  type RefinerLibraryWrite,
  type RefinerRuleSet,
  type RefinerRuleSetWrite,
} from "./libraries-api";
import { previewRefinerRules } from "./rules-preview-api";

export const refinerLibrariesKey = ["refiner", "libraries"];
export const refinerRuleSetsKey = ["refiner", "rule-sets"];

/** Asks the linked managers what they can do, so only while the option is on screen. */
export function useRefinerRejectSupportQuery(
  connectionIds: number[],
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["refiner", "reject-support", ...connectionIds],
    queryFn: () => fetchRefinerRejectSupport(connectionIds),
    enabled,
    staleTime: 60_000,
  });
}

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
    mutationFn: (data: RefinerLibraryCreate) => createRefinerLibrary(data),
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

/** "Try on a file" (#502). No cache: every call is a fresh, read-only probe. */
export function useRefinerRulesPreview() {
  return useMutation({ mutationFn: previewRefinerRules });
}
