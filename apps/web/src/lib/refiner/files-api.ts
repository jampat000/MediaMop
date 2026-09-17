import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export type RefinerFileStatus =
  | "unprocessed"
  | "processing"
  | "processed"
  | "processing_failed"
  | "skipped"
  | "disabled"
  | "on_hold"
  | "out_of_schedule"
  | "blocked_upstream"
  | "passed_through"
  | "rejected";

/** Plain words for each state. The reason string carries the detail. */
export const REFINER_FILE_STATUS_LABELS: Record<RefinerFileStatus, string> = {
  unprocessed: "Waiting",
  processing: "Processing",
  processed: "Done",
  processing_failed: "Failed",
  skipped: "Skipped",
  disabled: "Library off",
  on_hold: "On hold",
  out_of_schedule: "Out of schedule",
  blocked_upstream: "Blocked upstream",
  passed_through: "Handed back unchanged",
  rejected: "Rejected for a replacement",
};

/** Whether one device the operator owns will play the file without the media server converting it. */
export type RefinerDirectPlayVerdict = "yes" | "no" | "maybe" | "unknown";

/** Information only: this never changes what Weir does to a file. */
export interface RefinerDirectPlay {
  device_id: string;
  device_name: string;
  /** `maybe` means partial or model-dependent support; `unknown` means not measured yet. */
  verdict: RefinerDirectPlayVerdict;
  /** Plain words such as "cannot play DTS audio". Empty for `yes` and `unknown`. */
  reasons: string[];
}

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
  /** The collision policy in force and what it decided, kept on the file rather than only in an activity note. */
  output_collision_policy: string | null;
  output_collision_action: string | null;
  output_collision_reason: string | null;
  video_width: number | null;
  video_height: number | null;
  /** What the file is, measured at the last probe. Null means not probed yet, never zero. */
  video_codec: string | null;
  audio_track_count: number | null;
  subtitle_track_count: number | null;
  duration_seconds: number | null;
  /** One entry per device the operator chose. Empty when none are chosen. */
  direct_play: RefinerDirectPlay[];
  /** How far the pass currently working on this file has got. Null when nothing is in flight. */
  progress_percent: number | null;
  progress_message: string | null;
  progress_eta_seconds: number | null;
  /** When an on-hold file becomes eligible. Null when the wait is on a writer, not the clock. */
  hold_until: string | null;
  size_changed_at: string | null;
  /** When Weir first added this file to the workbench. */
  created_at: string;
  /** When this workbench row last changed state or detail. */
  updated_at: string;
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
  await requireOk(path, r, "Could not load files");
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

/** One plain-language step, written by the backend from the stored pass record. */
export interface RefinerFileStoryStep {
  heading: string;
  sentence: string;
  /** How the step should read — not a severity. */
  tone: "neutral" | "good" | "warn" | "bad";
}

export interface RefinerFileLogEntry {
  id: number;
  recorded_at: string;
  outcome: string;
  title: string;
  library_name: string;
  detail: Record<string, unknown>;
  /** The same pass told in plain language. Empty for a record with nothing to narrate. */
  story: RefinerFileStoryStep[];
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

/** One ffprobe stream on a held file (issue #501), with what the saved rules would do to it and why. */
export interface RefinerFileTrack {
  index: number;
  /** video, audio, subtitle, image, attachment or other. Only video, audio and subtitle can be chosen. */
  type: "video" | "audio" | "subtitle" | "image" | "attachment" | "other";
  codec: string | null;
  language: string | null;
  title: string | null;
  /** Audio only. */
  channels: number | null;
  /** The stream's own disposition on the held source, not what the rules would choose. */
  default: boolean;
  forced: boolean;
  rule_would_keep: boolean;
  rule_reason: string;
}

export interface RefinerFileTracks {
  file_id: number;
  relative_path: string;
  media_scope: string;
  source_fingerprint: {
    device: number;
    inode: number;
    size_bytes: number;
    modified_time_ns: number;
  };
  streams: RefinerFileTrack[];
}

export async function fetchRefinerFileTracks(
  id: number,
): Promise<RefinerFileTracks> {
  const path = `${refinerFilesPath()}/${id}/tracks`;
  const response = await apiFetch(path);
  await requireOk(path, response, "Could not read that file's tracks");
  return readJson<RefinerFileTracks>(response);
}

export interface RefinerManualPlanKeep {
  index: number;
  default: boolean;
  forced: boolean;
}

export interface RefinerManualPlanChoice {
  keep: RefinerManualPlanKeep[];
  order: number[];
}

export interface RefinerManualPlanResult {
  ok: boolean;
  job_id: number;
  dedupe_key: string;
  job_kind: string;
}

export async function postRefinerManualPlan(
  id: number,
  choice: RefinerManualPlanChoice,
): Promise<RefinerManualPlanResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerFilesPath()}/${id}/manual-plan`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...choice, csrf_token }),
  });
  await requireOk(path, response, "Could not queue that track choice");
  return readJson<RefinerManualPlanResult>(response);
}
