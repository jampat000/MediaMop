import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export type RefinerFileStatus =
  | "unprocessed"
  | "processing"
  | "processed"
  | "processing_failed"
  | "disabled"
  | "on_hold"
  | "out_of_schedule"
  | "blocked_upstream";

/** Plain words for each state. The reason string carries the detail. */
export const REFINER_FILE_STATUS_LABELS: Record<RefinerFileStatus, string> = {
  unprocessed: "Waiting",
  processing: "Processing",
  processed: "Done",
  processing_failed: "Failed",
  disabled: "Library off",
  on_hold: "On hold",
  out_of_schedule: "Out of schedule",
  blocked_upstream: "Blocked upstream",
};

export interface RefinerFile {
  id: number;
  library_id: number;
  library_name: string;
  relative_path: string;
  status: RefinerFileStatus;
  status_reason: string;
  blocked_by_connection: string | null;
  size_bytes: number;
  failure_class: string | null;
  failure_attempts: number;
  next_retry_at: string | null;
  video_width: number | null;
  video_height: number | null;
  /** When an on-hold file becomes eligible. Null when the wait is on a writer, not the clock. */
  hold_until: string | null;
  size_changed_at: string | null;
  last_seen_at: string | null;
  last_attempt_at: string | null;
}

export interface RefinerFilesPage {
  files: RefinerFile[];
  status_counts: Record<string, number>;
  returned: number;
  limit: number;
}

export interface RefinerFilesQuery {
  library_id?: number;
  file_status?: RefinerFileStatus;
  path_contains?: string;
  within_days?: number;
  limit?: number;
}

export const refinerFilesPath = () => "/api/v1/refiner/files";

export async function fetchRefinerFiles(
  query: RefinerFilesQuery = {},
): Promise<RefinerFilesPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const suffix = params.toString();
  const path = suffix ? `${refinerFilesPath()}?${suffix}` : refinerFilesPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner files");
  return readJson<RefinerFilesPage>(r);
}

export async function forgetRefinerFile(id: number): Promise<void> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerFilesPath()}/${id}`;
  const r = await apiFetch(path, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not remove that file from the list");
}

export interface RefinerFileMoveToTopResult {
  moved: boolean;
  detail: string;
}

export async function moveRefinerFileToTop(
  id: number,
): Promise<RefinerFileMoveToTopResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerFilesPath()}/${id}/move-to-top`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(
    path,
    response,
    "Could not move that file to the front of the queue",
  );
  return readJson<RefinerFileMoveToTopResult>(response);
}

export interface RefinerRequeueResult {
  requeued: number;
  skipped: number;
  detail: string;
}

export async function requeueRefinerFile(
  id: number,
): Promise<RefinerRequeueResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerFilesPath()}/${id}/requeue`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, response, "Could not queue that file again");
  return readJson<RefinerRequeueResult>(response);
}

export interface RefinerBulkRequeueQuery {
  library_id?: number;
  file_status?: RefinerFileStatus;
  path_contains?: string;
  limit?: number;
}

export async function requeueRefinerFiles(
  query: RefinerBulkRequeueQuery,
): Promise<RefinerRequeueResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerFilesPath()}/requeue`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...query, csrf_token }),
  });
  await requireOk(path, response, "Could not queue those files again");
  return readJson<RefinerRequeueResult>(response);
}

export interface RefinerWhyHeld {
  file_id: number;
  relative_path: string;
  library_name: string;
  recorded_status: string;
  recorded_reason: string;
  verdict: "proceed" | "wait_upstream" | "not_held" | "no_upstream_signal";
  owned: boolean;
  blocked_upstream: boolean;
  blocked_by_connection: string | null;
  queue_row_count: number;
  managers_consulted: number;
  managers_reporting: number;
  managers_without_queue_signal: string[];
  reasons: string[];
}

export async function fetchRefinerWhyHeld(id: number): Promise<RefinerWhyHeld> {
  const path = `${refinerFilesPath()}/${id}/why-held`;
  const response = await apiFetch(path);
  await requireOk(path, response, "Could not ask why that file is held");
  return readJson<RefinerWhyHeld>(response);
}

export interface RefinerFileLogEntry {
  id: number;
  recorded_at: string;
  outcome: string;
  title: string;
  library_name: string;
  detail: Record<string, unknown>;
}

export interface RefinerFileLog {
  file_id: number;
  relative_path: string;
  /** 0 means these records are kept forever. */
  retention_days: number;
  entries: RefinerFileLogEntry[];
}

export async function fetchRefinerFileLog(id: number): Promise<RefinerFileLog> {
  const path = `${refinerFilesPath()}/${id}/log`;
  const response = await apiFetch(path);
  await requireOk(
    path,
    response,
    "Could not read that file's processing record",
  );
  return readJson<RefinerFileLog>(response);
}

/** The plain-text record, for attaching to a bug report. */
export function refinerFileLogDownloadPath(id: number): string {
  return `${refinerFilesPath()}/${id}/log/download`;
}
