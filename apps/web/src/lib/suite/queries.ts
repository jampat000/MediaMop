import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchConfigurationBackupList,
  fetchSuiteSecurityOverview,
  fetchSuiteSettings,
  putSuiteSettings,
} from "./suite-settings-api";
import type { SuiteSettingsPutBody } from "./types";

export const suiteSettingsQueryKey = ["suite", "settings"] as const;
export const suiteSecurityOverviewQueryKey = ["suite", "security-overview"] as const;
export const suiteConfigurationBackupsQueryKey = ["suite", "configuration-backups"] as const;

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

export function useSuiteSettingsSaveMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SuiteSettingsPutBody) => putSuiteSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(suiteSettingsQueryKey, data);
    },
  });
}
