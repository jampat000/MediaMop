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
