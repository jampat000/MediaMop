import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchConfigurationBackupList,
  fetchSuiteLogs,
  fetchSuiteMetrics,
  fetchSuiteSecurityOverview,
  fetchSuiteSettings,
  fetchSuiteUpdateStatus,
  putSuiteSettings,
  startSuiteUpdateNow,
} from "./suite-settings-api";
import type { SuiteSettingsPutBody } from "./types";

export const suiteSettingsQueryKey = ["suite", "settings"] as const;
export const suiteSecurityOverviewQueryKey = ["suite", "security-overview"] as const;
export const suiteConfigurationBackupsQueryKey = ["suite", "configuration-backups"] as const;
export const suiteUpdateStatusQueryKey = ["suite", "update-status"] as const;
export const suiteLogsQueryKey = ["suite", "logs"] as const;
export const suiteMetricsQueryKey = ["suite", "metrics"] as const;

export function useSuiteSettingsQuery() {
  return useQuery({
    queryKey: suiteSettingsQueryKey,
    queryFn: () => fetchSuiteSettings(),
    staleTime: 30_000,
  });
}

export function useSuiteSecurityOverviewQuery() {
  return useQuery({
    queryKey: suiteSecurityOverviewQueryKey,
    queryFn: () => fetchSuiteSecurityOverview(),
    staleTime: 30_000,
  });
}

export function useSuiteConfigurationBackupsQuery(enabled: boolean) {
  return useQuery({
    queryKey: suiteConfigurationBackupsQueryKey,
    queryFn: () => fetchConfigurationBackupList(),
    enabled,
    staleTime: 15_000,
  });
}

export function useSuiteUpdateStatusQuery(enabled = true) {
  return useQuery({
    queryKey: suiteUpdateStatusQueryKey,
    queryFn: () => fetchSuiteUpdateStatus(),
    enabled,
    staleTime: 60_000,
    retry: false,
  });
}

export function useSuiteUpdateNowMutation() {
  return useMutation({
    mutationFn: () => startSuiteUpdateNow(),
  });
}

export function useSuiteLogsQuery(
  filters: {
    level?: string;
    search?: string;
    has_exception?: boolean;
    limit?: number;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: [...suiteLogsQueryKey, filters] as const,
    queryFn: () => fetchSuiteLogs(filters),
    enabled,
    refetchInterval: enabled ? 5000 : false,
    staleTime: 2000,
    retry: false,
  });
}

export function useSuiteMetricsQuery(enabled = true) {
  return useQuery({
    queryKey: suiteMetricsQueryKey,
    queryFn: () => fetchSuiteMetrics(),
    enabled,
    staleTime: 5000,
    refetchInterval: enabled ? 10000 : false,
    retry: false,
  });
}

export function useSuiteSettingsSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SuiteSettingsPutBody) => putSuiteSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(suiteSettingsQueryKey, data);
    },
  });
}
