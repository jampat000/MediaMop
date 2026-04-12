/** Shapes for Fetcher failed-import queue workflow APIs (JSON field names follow backend Pydantic models). */

/** GET /api/v1/fetcher/failed-imports/settings — settings snapshot from loaded config (not liveness). */
export type FailedImportFetcherSettingsOut = {
  background_job_worker_count: number;
  in_process_workers_disabled: boolean;
  in_process_workers_enabled: boolean;
  worker_mode_summary: string;
  failed_import_radarr_cleanup_drive_schedule_enabled: boolean;
  failed_import_radarr_cleanup_drive_schedule_interval_seconds: number;
  failed_import_sonarr_cleanup_drive_schedule_enabled: boolean;
  failed_import_sonarr_cleanup_drive_schedule_interval_seconds: number;
  visibility_note: string;
};

export type FailedImportManualQueuePassOut = {
  job_id: number;
  dedupe_key: string;
  job_kind: string;
  queue_outcome: "created" | "already_present";
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

export type FailedImportCleanupPolicyAxis = {
  remove_quality_rejections: boolean;
  remove_unmatched_manual_import_rejections: boolean;
  remove_corrupt_imports: boolean;
  remove_failed_downloads: boolean;
  remove_failed_imports: boolean;
};

export type FetcherFailedImportCleanupPolicyOut = {
  movies: FailedImportCleanupPolicyAxis;
  tv_shows: FailedImportCleanupPolicyAxis;
  updated_at: string;
};

/** PUT body (CSRF added by putFailedImportCleanupPolicy). */
export type FetcherFailedImportCleanupPolicyPutBody = {
  movies: FailedImportCleanupPolicyAxis;
  tv_shows: FailedImportCleanupPolicyAxis;
};
