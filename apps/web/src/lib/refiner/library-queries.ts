import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  cleanLibraryFiles,
  fetchLibraryFiles,
  fetchLibraryOverview,
  fetchLibraryProblems,
  fetchLibraryRedownloads,
  fetchLibrarySettings,
  requestLibraryRedownload,
  saveLibraryFolders,
  saveLibrarySettings,
  setLibrarySchedule,
  triggerLibraryScan,
  type LibraryFileFilters,
} from "./library-api";

export const librarySettingsKey = (libraryId: number) => [
  "refiner",
  "library-settings",
  libraryId,
];

export const libraryFilesKey = (
  libraryId: number,
  filters: LibraryFileFilters,
) => ["refiner", "library-files", libraryId, filters];

export const libraryOverviewKey = (libraryId: number) => [
  "refiner",
  "library-overview",
  libraryId,
];

export const libraryProblemsKey = (libraryId: number) => [
  "refiner",
  "library-problems",
  libraryId,
];

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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: librarySettingsKey(libraryId) });
      // clean_hardlinked_files decides whether seeding counts as a problem at all (#568).
      void qc.invalidateQueries({ queryKey: libraryProblemsKey(libraryId) });
      void qc.invalidateQueries({ queryKey: libraryOverviewKey(libraryId) });
    },
  });
}

/** Everything the Library view reads about one library, invalidated together after a scan or a clean. */
function invalidateLibraryViews(
  qc: ReturnType<typeof useQueryClient>,
  libraryId: number,
) {
  for (const key of [
    ["refiner", "library-files", libraryId],
    libraryOverviewKey(libraryId),
    libraryProblemsKey(libraryId),
  ]) {
    void qc.invalidateQueries({ queryKey: key });
  }
}

export function useTriggerLibraryScan(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => triggerLibraryScan(libraryId),
    onSuccess: () => invalidateLibraryViews(qc, libraryId),
  });
}

export function useLibraryFilesQuery(
  libraryId: number,
  filters: LibraryFileFilters,
  enabled = true,
) {
  return useQuery({
    queryKey: libraryFilesKey(libraryId, filters),
    queryFn: () => fetchLibraryFiles(libraryId, filters),
    enabled: enabled && libraryId > 0,
    // Changing a sort, a filter or the page makes a new query key. Without this the table would blank out
    // and fall back to its empty state for a moment on every one of those, which reads as "no files".
    placeholderData: keepPreviousData,
  });
}

/**
 * #568's Overview. `refetchInterval` follows the scan: while one is queued or running the totals and
 * breakdowns are still changing, so the page polls; once it finishes, polling stops.
 */
export function useLibraryOverviewQuery(libraryId: number, enabled = true) {
  return useQuery({
    queryKey: libraryOverviewKey(libraryId),
    queryFn: () => fetchLibraryOverview(libraryId),
    enabled: enabled && libraryId > 0,
    refetchInterval: (query) =>
      query.state.data?.scan?.running ? 3000 : false,
  });
}

/** #568's Problems view. */
export function useLibraryProblemsQuery(libraryId: number, enabled = true) {
  return useQuery({
    queryKey: libraryProblemsKey(libraryId),
    queryFn: () => fetchLibraryProblems(libraryId),
    enabled: enabled && libraryId > 0,
  });
}

export function useCleanLibraryFiles(libraryId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ paths, confirm }: { paths: string[]; confirm: boolean }) =>
      cleanLibraryFiles(libraryId, paths, confirm),
    onSuccess: () => invalidateLibraryViews(qc, libraryId),
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
