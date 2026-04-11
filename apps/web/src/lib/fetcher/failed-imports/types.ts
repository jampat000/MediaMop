/** Shapes for Fetcher failed-import queue workflow APIs (JSON field names follow backend). */

export type FailedImportTaskRow = {
  id: number;
  dedupe_key: string;
  job_kind: string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  lease_owner: string | null;
  lease_expires_at: string | null;
  last_error: string | null;
  payload_json: string | null;
  created_at: string;
  updated_at: string;
};

export type FailedImportTasksInspectionOut = {
  jobs: FailedImportTaskRow[];
  default_terminal_only: boolean;
};

/** GET /api/v1/fetcher/failed-imports/settings — same payload shape as legacy refiner visibility (settings keys unchanged). */
export type FailedImportFetcherSettingsOut = {
  refiner_worker_count: number;
  in_process_workers_disabled: boolean;
  in_process_workers_enabled: boolean;
  worker_mode_summary: string;
  refiner_radarr_cleanup_drive_schedule_enabled: boolean;
  refiner_radarr_cleanup_drive_schedule_interval_seconds: number;
  refiner_sonarr_cleanup_drive_schedule_enabled: boolean;
  refiner_sonarr_cleanup_drive_schedule_interval_seconds: number;
  visibility_note: string;
};

export type FailedImportEnqueueOut = {
  job_id: number;
  dedupe_key: string;
  job_kind: string;
  enqueue_outcome: "created" | "already_present";
};

export type FetcherFailedImportAxisSummary = {
  last_finished_at: string | null;
  last_outcome_label: string;
  saved_schedule_primary: string;
  saved_schedule_secondary: string | null;
};

export type FetcherFailedImportAutomationSummary = {
  scope_note: string;
  automation_slots_note: string | null;
  movies: FetcherFailedImportAxisSummary;
  tv_shows: FetcherFailedImportAxisSummary;
};
