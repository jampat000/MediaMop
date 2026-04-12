import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFailedImportAutomationSummary } from "./automation-summary-api";
import {
  fetchFailedImportCleanupPolicy,
  putFailedImportCleanupPolicy,
} from "./cleanup-policy-api";
import { postFailedImportRadarrEnqueue, postFailedImportSonarrEnqueue } from "./manual-enqueue-api";
import { fetchFailedImportFetcherSettings } from "./settings-api";
import { postFailedImportRecoverFinalize } from "./recover-api";

export const failedImportSettingsQueryKey = ["fetcher", "failed-imports", "settings"] as const;

export const failedImportAutomationSummaryQueryKey = ["fetcher", "failed-imports", "automation-summary"] as const;

export const failedImportCleanupPolicyQueryKey = ["fetcher", "failed-imports", "cleanup-policy"] as const;

export function useFailedImportAutomationSummaryQuery() {
  return useQuery({
    queryKey: failedImportAutomationSummaryQueryKey,
    queryFn: () => fetchFailedImportAutomationSummary(),
    staleTime: 15_000,
  });
}

export function useFailedImportCleanupPolicyQuery() {
  return useQuery({
    queryKey: failedImportCleanupPolicyQueryKey,
    queryFn: () => fetchFailedImportCleanupPolicy(),
    staleTime: 30_000,
  });
}

export function useFailedImportCleanupPolicySaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: putFailedImportCleanupPolicy,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: failedImportCleanupPolicyQueryKey });
    },
  });
}

export function useFailedImportFetcherSettingsQuery() {
  return useQuery({
    queryKey: failedImportSettingsQueryKey,
    queryFn: () => fetchFailedImportFetcherSettings(),
    staleTime: 30_000,
  });
}

export function useFailedImportRecoverMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => postFailedImportRecoverFinalize(jobId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["fetcher", "jobs", "inspection"] });
      void qc.invalidateQueries({ queryKey: failedImportAutomationSummaryQueryKey });
    },
  });
}

export function useFailedImportRadarrEnqueueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postFailedImportRadarrEnqueue(),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["fetcher", "jobs", "inspection"] });
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
      void qc.invalidateQueries({ queryKey: ["fetcher", "jobs", "inspection"] });
      void qc.invalidateQueries({ queryKey: ["fetcher", "failed-imports", "settings"] });
      void qc.invalidateQueries({ queryKey: failedImportAutomationSummaryQueryKey });
    },
  });
}
