import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dashboardStatusKey } from "../dashboard/queries";
import {
  createNotificationChannel,
  deleteNotificationChannel,
  fetchConfigurationBackupList,
  fetchNotificationChannels,
  fetchSuiteLogs,
  fetchSuiteMetrics,
  fetchSuiteSecurityOverview,
  fetchSuiteSettings,
  fetchSuiteUpdateStatus,
  putSuiteSettings,
  resetSuiteOperationalHistory,
  testNotificationChannel,
  updateNotificationChannel,
} from "./suite-settings-api";
import type { NotificationChannelIn, SuiteSettingsPutBody } from "./types";

export const suiteSettingsQueryKey = ["suite", "settings"] as const;
export const suiteSecurityOverviewQueryKey = [
  "suite",
  "security-overview",
] as const;
export const suiteConfigurationBackupsQueryKey = [
  "suite",
  "configuration-backups",
] as const;
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

export function useSuiteUpdateStatusQuery(
  enabled = true,
  refetchInterval: number | false = false,
) {
  return useQuery({
    queryKey: suiteUpdateStatusQueryKey,
    queryFn: () => fetchSuiteUpdateStatus(),
    enabled,
    staleTime: enabled && refetchInterval ? 0 : 60_000,
    refetchInterval,
    retry: false,
  });
}

export function useSuiteOperationalHistoryResetMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (confirm: string) => resetSuiteOperationalHistory(confirm),
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: suiteMetricsQueryKey }),
        qc.invalidateQueries({ queryKey: dashboardStatusKey }),
      ]);
    },
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

export const suiteNotificationChannelsQueryKey = [
  "suite",
  "notification-channels",
] as const;

export function useSuiteNotificationChannelsQuery(enabled = true) {
  return useQuery({
    queryKey: suiteNotificationChannelsQueryKey,
    queryFn: () => fetchNotificationChannels(),
    enabled,
    staleTime: 30_000,
  });
}

export function useCreateNotificationChannelMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: NotificationChannelIn) =>
      createNotificationChannel(data),
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: suiteNotificationChannelsQueryKey,
      });
    },
  });
}

export function useUpdateNotificationChannelMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: NotificationChannelIn }) =>
      updateNotificationChannel(id, data),
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: suiteNotificationChannelsQueryKey,
      });
    },
  });
}

export function useDeleteNotificationChannelMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteNotificationChannel(id),
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: suiteNotificationChannelsQueryKey,
      });
    },
  });
}

export function useTestNotificationChannelMutation() {
  return useMutation({
    mutationFn: (id: number) => testNotificationChannel(id),
  });
}

export function useSuiteSettingsSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SuiteSettingsPutBody) => putSuiteSettings(body),
    onSuccess: async (data) => {
      qc.setQueryData(suiteSettingsQueryKey, data);
      await qc.invalidateQueries({ queryKey: suiteSettingsQueryKey });
    },
  });
}
