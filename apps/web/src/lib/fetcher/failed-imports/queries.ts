import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFailedImportAutomationSummary } from "./automation-summary-api";
import { fetchFailedImportTasksInspection } from "./inspection-api";
import { postFailedImportRadarrEnqueue, postFailedImportSonarrEnqueue } from "./manual-enqueue-api";
import { fetchFailedImportFetcherSettings } from "./settings-api";
import { postFailedImportRecoverFinalize } from "./recover-api";

/** terminal = omit status param — server returns completed, failed, handler_ok_finalize_failed only. */
export type FailedImportInspectionFilter =
  | "terminal"
  | "pending"
  | "leased"
  | "completed"
  | "failed"
  | "handler_ok_finalize_failed";

export const failedImportInspectionQueryKey = (filter: FailedImportInspectionFilter) =>
  ["fetcher", "failed-imports", "inspection", filter] as const;

export const failedImportSettingsQueryKey = ["fetcher", "failed-imports", "settings"] as const;

export const failedImportAutomationSummaryQueryKey = ["fetcher", "failed-imports", "automation-summary"] as const;

export function useFailedImportAutomationSummaryQuery() {
  return useQuery({
    queryKey: failedImportAutomationSummaryQueryKey,
    queryFn: () => fetchFailedImportAutomationSummary(),
    staleTime: 15_000,
  });
}

export function useFailedImportFetcherSettingsQuery() {
  return useQuery({
    queryKey: failedImportSettingsQueryKey,
    queryFn: () => fetchFailedImportFetcherSettings(),
    staleTime: 30_000,
  });
}

export function useFailedImportTasksInspectionQuery(filter: FailedImportInspectionFilter) {
  return useQuery({
    queryKey: failedImportInspectionQueryKey(filter),
    queryFn: () =>
      fetchFailedImportTasksInspection(
        filter === "terminal" ? { limit: 50 } : { limit: 50, statuses: [filter] },
      ),
    staleTime: 15_000,
  });
}

export function useFailedImportRecoverMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => postFailedImportRecoverFinalize(jobId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["fetcher", "failed-imports", "inspection"] });
      void qc.invalidateQueries({ queryKey: failedImportAutomationSummaryQueryKey });
    },
  });
}

export function useFailedImportRadarrEnqueueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postFailedImportRadarrEnqueue(),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["fetcher", "failed-imports", "inspection"] });
      void qc.invalidateQueries({ queryKey: ["fetcher", "failed-imports", "settings"] });
      void qc.invalidateQueries({ queryKey: failedImportAutomationSummaryQueryKey });
    },
  });
}

export function useFailedImportSonarrEnqueueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postFailedImportSonarrEnqueue(),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["fetcher", "failed-imports", "inspection"] });
      void qc.invalidateQueries({ queryKey: ["fetcher", "failed-imports", "settings"] });
      void qc.invalidateQueries({ queryKey: failedImportAutomationSummaryQueryKey });
    },
  });
}
