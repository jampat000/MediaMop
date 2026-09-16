import { fetchCsrfToken } from "./auth-api";
import { apiFetch, readJson, requireOk } from "./client";
import type {
  ActivityFileHistoryPreview,
  ActivityFileHistoryRemoved,
  ActivityRecentResponse,
} from "./types";

export type ActivityRecentFilters = {
  limit?: number;
  module?: string;
  event_type?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  before_id?: number;
  trigger?: string;
  result?: string;
  library_id?: number;
  file?: string;
};

/** The filters shared by the feed and the export, as query parameters. */
function activityFilterParams(
  options?: Omit<ActivityRecentFilters, "limit" | "before_id">,
): URLSearchParams {
  const q = new URLSearchParams();
  if (options?.module) q.set("module", options.module);
  if (options?.event_type) q.set("event_type", options.event_type);
  if (options?.search) q.set("search", options.search);
  if (options?.date_from) q.set("date_from", options.date_from);
  if (options?.date_to) q.set("date_to", options.date_to);
  if (options?.trigger) q.set("trigger", options.trigger);
  if (options?.result) q.set("result", options.result);
  if (options?.library_id !== undefined)
    q.set("library_id", String(Math.trunc(options.library_id)));
  if (options?.file) q.set("file", options.file);
  return q;
}

export function activityRecentPath(options?: ActivityRecentFilters): string {
  const q = activityFilterParams(options);
  const lim = options?.limit;
  if (lim !== undefined && Number.isFinite(lim)) {
    q.set("limit", String(Math.trunc(lim)));
  }
  if (options?.before_id !== undefined)
    q.set("before_id", String(Math.trunc(options.before_id)));
  const qs = q.toString();
  return qs ? `/api/v1/activity/recent?${qs}` : "/api/v1/activity/recent";
}

export async function fetchActivityRecent(
  options?: ActivityRecentFilters,
): Promise<ActivityRecentResponse> {
  const path = activityRecentPath(options);
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load activity");
  return readJson<ActivityRecentResponse>(r);
}

export function activityExportPath(
  format: "csv" | "json",
  options?: ActivityRecentFilters,
): string {
  const q = activityFilterParams(options);
  q.set("format", format);
  return `/api/v1/activity/export?${q.toString()}`;
}

function filenameFromDisposition(
  header: string | null,
  fallback: string,
): string {
  const match = header?.match(/filename="?([^";]+)"?/i);
  return match?.[1]?.trim() || fallback;
}

/** The filtered history as a file. The caller hands the blob to the browser. */
export async function fetchActivityExport(
  format: "csv" | "json",
  options?: ActivityRecentFilters,
): Promise<{ blob: Blob; filename: string }> {
  const path = activityExportPath(format, options);
  const r = await apiFetch(path, {
    headers: {
      Accept: format === "json" ? "application/json" : "text/csv",
    },
  });
  await requireOk(path, r, "Could not export activity");
  return {
    blob: await r.blob(),
    filename: filenameFromDisposition(
      r.headers.get("Content-Disposition"),
      `mediamop-activity.${format}`,
    ),
  };
}

type FileHistoryTarget = { relative_path: string; library_id?: number | null };

/** What removing one file's history would delete. Removes nothing. */
export async function fetchActivityFileHistoryPreview(
  target: FileHistoryTarget,
): Promise<ActivityFileHistoryPreview> {
  const q = new URLSearchParams({ relative_path: target.relative_path });
  if (target.library_id != null) q.set("library_id", String(target.library_id));
  const path = `/api/v1/activity/file-history?${q.toString()}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not check this file's history");
  return readJson<ActivityFileHistoryPreview>(r);
}

export async function removeActivityFileHistory(
  target: FileHistoryTarget,
): Promise<ActivityFileHistoryRemoved> {
  const csrf_token = await fetchCsrfToken();
  const path = "/api/v1/activity/file-history/remove";
  const body: Record<string, unknown> = {
    csrf_token,
    relative_path: target.relative_path,
  };
  if (target.library_id != null) body.library_id = target.library_id;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await requireOk(path, r, "Could not remove this file's history");
  return readJson<ActivityFileHistoryRemoved>(r);
}
