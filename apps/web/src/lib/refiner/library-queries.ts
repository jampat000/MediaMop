import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cleanLibraryFiles,
  fetchLibraryFiles,
  fetchLibraryRedownloads,
  fetchLibrarySettings,
  requestLibraryRedownload,
  saveLibraryFolders,
  saveLibrarySettings,
  setLibrarySchedule,
  triggerLibraryScan,
  type LibraryFileClassification,
} from "./library-api";

export const librarySettingsKey = (libraryId: number) => [
  "refiner",
  "library-settings",
  libraryId,
];

export const libraryFilesKey = (
  libraryId: number,
  filters: {
    classification?: LibraryFileClassification;
    manager?: string;
    q?: string;
  },
) => ["refiner", "library-files", libraryId, filters];

export function useLibrarySettingsQuery(libraryId: number, enabled = true) {
  return useQuery({
    queryKey: librarySettingsKey(libraryId),
    queryFn: () => fetchLibrarySettings(libraryId),
    enabled: enabled && libraryId > 0,
  });
}

export function useSaveLibraryFolders(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (folders: string[]) => saveLibraryFolders(libraryId, folders),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: librarySettingsKey(libraryId) }),
  });
}

/** #508: the two preflight checkboxes, saved together with the library's current folders (see saveLibrarySettings). */
export function useSaveLibraryPreflightSettings(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (updates: {
      library_folders: string[];
      clean_hardlinked_files?: boolean;
      skip_if_manager_would_redownload?: boolean;
    }) => saveLibrarySettings(libraryId, updates),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: librarySettingsKey(libraryId) }),
  });
}

export function useTriggerLibraryScan(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => triggerLibraryScan(libraryId),
    onSuccess: () =>
      void qc.invalidateQueries({
        queryKey: ["refiner", "library-files", libraryId],
      }),
  });
}

export function useLibraryFilesQuery(
  libraryId: number,
  filters: {
    classification?: LibraryFileClassification;
    manager?: string;
    q?: string;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: libraryFilesKey(libraryId, filters),
    queryFn: () => fetchLibraryFiles(libraryId, filters),
    enabled: enabled && libraryId > 0,
  });
}

export function useCleanLibraryFiles(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ paths, confirm }: { paths: string[]; confirm: boolean }) =>
      cleanLibraryFiles(libraryId, paths, confirm),
    onSuccess: (result) => {
      if (result.kind === "cleaned") {
        void qc.invalidateQueries({
          queryKey: ["refiner", "library-files", libraryId],
        });
      }
    },
  });
}

export const libraryRedownloadsKey = (libraryId: number) => [
  "refiner",
  "library-redownloads",
  libraryId,
];

/** #509 step 2: titles a rule change now keeps a track for that a past clean removed. */
export function useLibraryRedownloadsQuery(libraryId: number, enabled = true) {
  return useQuery({
    queryKey: libraryRedownloadsKey(libraryId),
    queryFn: () => fetchLibraryRedownloads(libraryId),
    enabled: enabled && libraryId > 0,
  });
}

/** #509 step 3: "Download again", shown only when the title's can_redownload is true. */
export function useRequestLibraryRedownload(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => requestLibraryRedownload(libraryId, path),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: libraryRedownloadsKey(libraryId) }),
  });
}

export function useSetLibrarySchedule(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      enabled,
      confirm,
    }: {
      enabled: boolean;
      confirm: boolean;
    }) => setLibrarySchedule(libraryId, enabled, confirm),
    onSuccess: (result) => {
      if (!("kind" in result)) {
        void qc.invalidateQueries({ queryKey: librarySettingsKey(libraryId) });
      }
    },
  });
}
