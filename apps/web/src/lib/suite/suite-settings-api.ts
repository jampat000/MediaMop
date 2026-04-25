import { fetchCsrfToken } from "../api/auth-api";
import { apiErrorDetailToString, apiFetch, readJson } from "../api/client";
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
export const suiteUpdateStatusPath = () => "/api/v1/suite/update-status";
export const suiteUpdateNowPath = () => "/api/v1/suite/update-now";
export const suiteLogsPath = () => "/api/v1/suite/logs";
export const suiteMetricsPath = () => "/api/v1/suite/metrics";

/**
 * GET/PUT configuration bundle — same handler on the backend, several URL aliases for older builds
 * and reverse proxies that only forward a subset of ``/api/v1/suite/*`` or ``/api/v1/system/*``.
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

async function readFailedRequestMessage(r: Response, fallback: string): Promise<string> {
  const ctype = (r.headers.get("content-type") || "").toLowerCase();
  if (ctype.includes("application/json")) {
    try {
      const b = (await r.clone().json()) as { detail?: unknown };
      const fromDetail = apiErrorDetailToString(b.detail);
      if (fromDetail.length > 0) {
        return fromDetail;
      }
    } catch {
      /* ignore */
    }
  }
  const text = await r.text();
  const t = text.trimStart();
  if (t.startsWith("<!") || t.toLowerCase().startsWith("<html")) {
    return `${fallback} (${r.status}) — received HTML instead of JSON. Use the same origin as the API (dev: Vite proxy to the backend) and restart the server after upgrading.`;
  }
  const oneLine = text.replace(/\s+/g, " ").trim().slice(0, 180);
  return oneLine.length > 0 ? `${fallback} (${r.status}): ${oneLine}` : `${fallback} (${r.status})`;
}

export async function fetchSuiteSettings(): Promise<SuiteSettingsOut> {
  const r = await apiFetch(suiteSettingsPath());
  if (!r.ok) {
    throw new Error(`Could not load suite settings (${r.status})`);
  }
  return readJson<SuiteSettingsOut>(r);
}

export async function putSuiteSettings(body: SuiteSettingsPutBody): Promise<SuiteSettingsOut> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(suiteSettingsPath(), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  if (!r.ok) {
    throw new Error(await readFailedRequestMessage(r, `Could not save suite settings (${r.status})`));
  }
  return readJson<SuiteSettingsOut>(r);
}

export async function fetchSuiteSecurityOverview(): Promise<SuiteSecurityOverviewOut> {
  const r = await apiFetch(suiteSecurityOverviewPath());
  if (!r.ok) {
    throw new Error(`Could not load security overview (${r.status})`);
  }
  return readJson<SuiteSecurityOverviewOut>(r);
}

export async function fetchSuiteUpdateStatus(): Promise<SuiteUpdateStatusOut> {
  const r = await apiFetch(suiteUpdateStatusPath());
  if (!r.ok) {
    throw new Error(await readFailedRequestMessage(r, "Could not check for updates"));
  }
  return readJson<SuiteUpdateStatusOut>(r);
}

export async function startSuiteUpdateNow(): Promise<SuiteUpdateStartOut> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(suiteUpdateNowPath(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  if (!r.ok) {
    throw new Error(await readFailedRequestMessage(r, "Could not start upgrade"));
  }
  return readJson<SuiteUpdateStartOut>(r);
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
  if (!r.ok) {
    throw new Error(await readFailedRequestMessage(r, "Could not load logs"));
  }
  return readJson<SuiteLogsOut>(r);
}

export async function fetchSuiteMetrics(): Promise<SuiteMetricsOut> {
  const r = await apiFetch(suiteMetricsPath());
  if (!r.ok) {
    throw new Error(await readFailedRequestMessage(r, "Could not load runtime health"));
  }
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
      throw new Error(await readFailedRequestMessage(r, "Could not export configuration"));
    }
    return readJson<ConfigurationBundle>(r);
  }
  throw new Error(await readFailedRequestMessage(last!, "Could not export configuration"));
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
      throw new Error(await readFailedRequestMessage(r, "Could not restore configuration"));
    }
    return readJson<ConfigurationBundle>(r);
  }
  throw new Error(await readFailedRequestMessage(last!, "Could not restore configuration"));
}

export async function fetchConfigurationBackupList(): Promise<SuiteConfigurationBackupListOut> {
  const r = await apiFetch(suiteConfigurationBackupsPath());
  if (!r.ok) {
    throw new Error(await readFailedRequestMessage(r, "Could not load automatic snapshots"));
  }
  return readJson<SuiteConfigurationBackupListOut>(r);
}

export async function fetchStoredConfigurationBackupBlob(backupId: number): Promise<Blob> {
  const r = await apiFetch(`${suiteConfigurationBackupsPath()}/${backupId}/download`);
  if (!r.ok) {
    throw new Error(await readFailedRequestMessage(r, "Could not download automatic snapshot"));
  }
  return r.blob();
}
