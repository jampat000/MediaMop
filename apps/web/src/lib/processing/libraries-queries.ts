import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createProcessingLibrary,
  createProcessingRuleSet,
  deleteProcessingLibrary,
  deleteProcessingRuleSet,
  discoverProcessingLibraries,
  fetchProcessingLibraryDrift,
  fetchProcessingManagerSetup,
  fetchProcessingRejectSupport,
  fetchProcessingLibraries,
  fetchProcessingRuleSets,
  importDiscoveredProcessingLibraries,
  reorderProcessingLibraries,
  unlinkDiscoveredProcessingLibrary,
  updateProcessingLibrary,
  updateProcessingRuleSet,
  type ProcessingLibrary,
  type ProcessingLibraryCreate,
  type ProcessingMediaType,
  type ProcessingLibraryWrite,
  type ProcessingRuleSet,
  type ProcessingRuleSetWrite,
} from "./libraries-api";
import { previewProcessingRules } from "./rules-preview-api";

export const processingLibrariesKey = ["processing", "libraries"];
export const processingRuleSetsKey = ["processing", "rule-sets"];

/** Asks the linked managers what they can do, so only while the option is on screen. */
export function useProcessingRejectSupportQuery(
  connectionIds: number[],
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["processing", "reject-support", ...connectionIds],
    queryFn: () => fetchProcessingRejectSupport(connectionIds),
    enabled,
    staleTime: 60_000,
  });
}

/**
 * Asks each connected media manager whether it will pick up what a library with these folders writes.
 * Only while the library editor is open, and keyed on the folders so a change is checked again.
 */
export function useProcessingManagerSetupQuery(
  mediaType: ProcessingMediaType,
  watchedFolder: string,
  outputFolder: string,
  removeOriginal: boolean,
  enabled: boolean,
) {
  return useQuery({
    queryKey: [
      "processing",
      "manager-setup",
      mediaType,
      watchedFolder,
      outputFolder,
      removeOriginal,
    ],
    queryFn: () =>
      fetchProcessingManagerSetup(
        mediaType,
        watchedFolder,
        outputFolder,
        removeOriginal,
      ),
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

export function useProcessingLibrariesQuery(enabled = true) {
  return useQuery<ProcessingLibrary[]>({
    queryKey: processingLibrariesKey,
    queryFn: fetchProcessingLibraries,
    enabled,
  });
}

export function useCreateProcessingLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProcessingLibraryCreate) =>
      createProcessingLibrary(data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingLibrariesKey }),
  });
}

export function useUpdateProcessingLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; data: ProcessingLibraryWrite }) =>
      updateProcessingLibrary(vars.id, vars.data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingLibrariesKey }),
  });
}

export function useDeleteProcessingLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteProcessingLibrary(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingLibrariesKey }),
  });
}

export function useReorderProcessingLibraries() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: number[]) => reorderProcessingLibraries(ids),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingLibrariesKey }),
  });
}

export function useDiscoverProcessingLibraries() {
  return useMutation({
    mutationFn: (connectionId: number) =>
      discoverProcessingLibraries(connectionId),
  });
}

export function useImportDiscoveredProcessingLibraries() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { connectionId: number; keys: string[] }) =>
      importDiscoveredProcessingLibraries(vars.connectionId, vars.keys),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingLibrariesKey }),
  });
}

export function useProcessingLibraryDrift() {
  return useMutation({
    mutationFn: (connectionId: number) =>
      fetchProcessingLibraryDrift(connectionId),
  });
}

export function useUnlinkDiscoveredProcessingLibrary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => unlinkDiscoveredProcessingLibrary(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingLibrariesKey }),
  });
}

export function useProcessingRuleSetsQuery() {
  return useQuery<ProcessingRuleSet[]>({
    queryKey: processingRuleSetsKey,
    queryFn: fetchProcessingRuleSets,
  });
}

export function useCreateProcessingRuleSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProcessingRuleSetWrite) => createProcessingRuleSet(data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingRuleSetsKey }),
  });
}

export function useUpdateProcessingRuleSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; data: ProcessingRuleSetWrite }) =>
      updateProcessingRuleSet(vars.id, vars.data),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: processingRuleSetsKey }),
  });
}

export function useDeleteProcessingRuleSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteProcessingRuleSet(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: processingRuleSetsKey });
      void qc.invalidateQueries({ queryKey: processingLibrariesKey });
    },
  });
}

/** "Try on a file" (#502). No cache: every call is a fresh, read-only probe. */
export function useProcessingRulesPreview() {
  return useMutation({ mutationFn: previewProcessingRules });
}
