import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk, throwApiResponseError } from "../api/client";
import type {
  SuiteConfigurationBackupListOut,
  SuiteLogsOut,
  SuiteMetricsOut,
  SuiteSecurityOverviewOut,
  SuiteSettingsOut,
  SuiteSettingsPutBody,
  SuiteUpdateStartOut,
  SuiteUpdateStatusOut,
} from "./types";

export const suiteSettingsPath = () => "/api/v1/suite/settings";
export const suiteSecurityOverviewPath = () => "/api/v1/suite/security-overview";
export const suiteUpdateStatusPaths = ["/api/v1/suite/update-status", "/api/v1/suite/settings/update-status"] as const;
export const suiteUpdateNowPaths = ["/api/v1/suite/update-now", "/api/v1/suite/settings/update-now"] as const;
export const suiteUpdateStatusPath = () => suiteUpdateStatusPaths[0];
export const suiteUpdateNowPath = () => suiteUpdateNowPaths[0];
export const suiteLogsPath = () => "/api/v1/suite/logs";
export const suiteMetricsPath = () => "/api/v1/suite/metrics";

/**
 * GET/PUT configuration bundle: same handler on the backend, several URL aliases for older builds
 * and reverse proxies that only forward a subset of `/api/v1/suite/*` or `/api/v1/system/*`.
 */
export const configurationBundlePaths = [
  "/api/v1/suite/configuration-bundle",
  "/api/v1/suite/settings/configuration-bundle",
  "/api/v1/system/suite-configuration-bundle",
] as const;

/** Preferred path (first entry in {@link configurationBundlePaths}). */
export const suiteConfigurationBundlePath = () => configurationBundlePaths[0];
export const suiteConfigurationBackupsPath = () => "/api/v1/suite/configuration-backups";

export type ConfigurationBundle = Record<string, unknown> & { format_version: number };

export async function fetchSuiteSettings(): Promise<SuiteSettingsOut> {
  const path = suiteSettingsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load suite settings");
  return readJson<SuiteSettingsOut>(r);
}

export async function putSuiteSettings(body: SuiteSettingsPutBody): Promise<SuiteSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const path = suiteSettingsPath();
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not save suite settings");
  return readJson<SuiteSettingsOut>(r);
}

export async function fetchSuiteSecurityOverview(): Promise<SuiteSecurityOverviewOut> {
  const path = suiteSecurityOverviewPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load security overview");
  return readJson<SuiteSecurityOverviewOut>(r);
}

export async function fetchSuiteUpdateStatus(): Promise<SuiteUpdateStatusOut> {
  let last: Response | undefined;
  for (const path of suiteUpdateStatusPaths) {
    const r = await apiFetch(path);
    last = r;
    if (r.status === 404) {
      continue;
    }
    if (!r.ok) {
      await throwApiResponseError(path, r, "Could not check for updates");
    }
    return readJson<SuiteUpdateStatusOut>(r);
  }
  return throwApiResponseError(suiteUpdateStatusPath(), last!, "Could not check for updates");
}

export async function startSuiteUpdateNow(): Promise<SuiteUpdateStartOut> {
  const csrf_token = await fetchCsrfToken();
  let last: Response | undefined;
  for (const path of suiteUpdateNowPaths) {
    const r = await apiFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csrf_token }),
    });
    last = r;
    if (r.status === 404) {
      continue;
    }
    if (!r.ok) {
      await throwApiResponseError(path, r, "Could not start upgrade");
    }
    return readJson<SuiteUpdateStartOut>(r);
  }
  return throwApiResponseError(suiteUpdateNowPath(), last!, "Could not start upgrade");
}

export async function fetchSuiteLogs(filters?: {
  level?: string;
  search?: string;
  has_exception?: boolean;
  limit?: number;
}): Promise<SuiteLogsOut> {
  const params = new URLSearchParams();
  if (filters?.level) params.set("level", filters.level);
  if (filters?.search) params.set("search", filters.search);
  if (typeof filters?.has_exception === "boolean") params.set("has_exception", String(filters.has_exception));
  if (typeof filters?.limit === "number") params.set("limit", String(filters.limit));
  const path = params.size > 0 ? `${suiteLogsPath()}?${params.toString()}` : suiteLogsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load logs");
  return readJson<SuiteLogsOut>(r);
}

export async function fetchSuiteMetrics(): Promise<SuiteMetricsOut> {
  const path = suiteMetricsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load runtime health");
  return readJson<SuiteMetricsOut>(r);
}

export async function fetchConfigurationBundle(): Promise<ConfigurationBundle> {
  let last: Response | undefined;
  for (const path of configurationBundlePaths) {
    const r = await apiFetch(path);
    last = r;
    if (r.status === 404) {
      continue;
    }
    if (!r.ok) {
      await throwApiResponseError(path, r, "Could not export configuration");
    }
    return readJson<ConfigurationBundle>(r);
  }
  return throwApiResponseError(suiteConfigurationBundlePath(), last!, "Could not export configuration");
}

export async function putConfigurationBundle(bundle: ConfigurationBundle): Promise<ConfigurationBundle> {
  const csrf_token = await fetchCsrfToken();
  let last: Response | undefined;
  for (const path of configurationBundlePaths) {
    const r = await apiFetch(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csrf_token, bundle }),
    });
    last = r;
    if (r.status === 404) {
      continue;
    }
    if (!r.ok) {
      await throwApiResponseError(path, r, "Could not restore configuration");
    }
    return readJson<ConfigurationBundle>(r);
  }
  return throwApiResponseError(suiteConfigurationBundlePath(), last!, "Could not restore configuration");
}

export async function fetchConfigurationBackupList(): Promise<SuiteConfigurationBackupListOut> {
  const path = suiteConfigurationBackupsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load automatic snapshots");
  return readJson<SuiteConfigurationBackupListOut>(r);
}

export async function fetchStoredConfigurationBackupBlob(backupId: number): Promise<Blob> {
  const path = `${suiteConfigurationBackupsPath()}/${backupId}/download`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not download automatic snapshot");
  return r.blob();
}
