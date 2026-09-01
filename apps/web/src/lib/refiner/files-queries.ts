import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { postRefinerFileRemuxPassEnqueue } from "./file-remux-pass-api";
import {
  fetchRefinerFiles,
  forgetRefinerFile,
  fetchRefinerFileLog,
  fetchRefinerWhyHeld,
  moveRefinerFileToTop,
  requeueRefinerFile,
  requeueRefinerFiles,
  type RefinerBulkRequeueQuery,
  type RefinerFilesPage,
  type RefinerFilesQuery,
} from "./files-api";
import { postRefinerWatchedFolderRemuxScanDispatchEnqueue } from "./watched-folder-scan-api";

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

export function useRequeueRefinerFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => requeueRefinerFile(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] }),
  });
}

export function useRequeueRefinerFiles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (query: RefinerBulkRequeueQuery) => requeueRefinerFiles(query),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] }),
  });
}

export function useRefinerWhyHeld() {
  // A mutation rather than a query: this asks the managers *right now*, and only when
  // someone asks. Running it on render would poll every connection for every file.
  return useMutation({ mutationFn: (id: number) => fetchRefinerWhyHeld(id) });
}

export function useRefinerFileLog() {
  // A mutation rather than a query: a processing record is read when someone opens it,
  // not for every row on every render.
  return useMutation({ mutationFn: (id: number) => fetchRefinerFileLog(id) });
}

export function useProcessRefinerFileNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      relative_media_path,
      media_scope,
      library_id,
      pass_through_unchanged,
    }: {
      relative_media_path: string;
      media_scope: "movie" | "tv";
      library_id?: number;
      pass_through_unchanged?: boolean;
    }) =>
      postRefinerFileRemuxPassEnqueue({
        relative_media_path,
        media_scope,
        library_id,
        pass_through_unchanged,
      }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] }),
  });
}

export function useRefinerCheckLibraryAgain() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      media_scope,
      library_id,
    }: {
      media_scope: "movie" | "tv";
      library_id: number;
    }) =>
      postRefinerWatchedFolderRemuxScanDispatchEnqueue({
        enqueue_remux_jobs: true,
        media_scope,
        library_id,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["refiner", "files"] });
      void qc.invalidateQueries({ queryKey: ["refiner", "jobs"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
