/** GET /api/v1/processing/runtime-settings — read-only Processing in-process worker snapshot. */

export type ProcessingRuntimeSettingsOut = {
  in_process_processing_worker_count: number;
  in_process_workers_disabled: boolean;
  in_process_workers_enabled: boolean;
  worker_mode_summary: string;
  sqlite_throughput_note: string;
  configuration_note: string;
  visibility_note: string;
  processing_media_extensions: string[];
  processing_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs: boolean;
  processing_watched_folder_min_file_age_seconds: number;
  processing_movie_output_cleanup_min_age_seconds: number;
  movie_output_cleanup_configuration_note: string;
  processing_tv_output_cleanup_min_age_seconds: number;
  tv_output_cleanup_configuration_note: string;
  watched_folder_scan_periodic_configuration_note: string;
  processing_work_temp_stale_sweep_movie_schedule_enabled: boolean;
  processing_work_temp_stale_sweep_movie_schedule_interval_seconds: number;
  processing_work_temp_stale_sweep_tv_schedule_enabled: boolean;
  processing_work_temp_stale_sweep_tv_schedule_interval_seconds: number;
  processing_work_temp_stale_sweep_min_stale_age_seconds: number;
  processing_movie_failure_cleanup_schedule_enabled: boolean;
  processing_movie_failure_cleanup_schedule_interval_seconds: number;
  processing_tv_failure_cleanup_schedule_enabled: boolean;
  processing_tv_failure_cleanup_schedule_interval_seconds: number;
  processing_movie_failure_cleanup_grace_period_seconds: number;
  processing_tv_failure_cleanup_grace_period_seconds: number;
  failure_cleanup_configuration_note: string;
  work_temp_stale_sweep_periodic_configuration_note: string;
};

export type ProcessingOverviewStatsOut = {
  window_days: number;
  files_processed: number;
  files_failed: number;
  success_rate_percent: number;
  output_written_count: number;
  already_optimized_count: number;
  net_space_saved_bytes: number;
  net_space_saved_percent: number;
};

export type ProcessingOperatorSettingsOut = {
  max_concurrent_files: number;
  runner_capacity: number;
  runner_cost_sd: number;
  runner_cost_720p: number;
  runner_cost_1080p: number;
  runner_cost_4k: number;
  runner_cost_undetermined: number;
  work_temp_stale_sweep_enabled: boolean;
  failure_cleanup_enabled: boolean;
  keep_failed_work_files: boolean;
  file_log_retention_days: number;
  verbose_detection_logging: boolean;
  min_file_age_seconds: number;
  min_input_file_size_mb: number;
  minimum_free_disk_space_mb: number;
  movie_schedule_enabled: boolean;
  movie_schedule_hours_limited: boolean;
  movie_schedule_days: string;
  movie_schedule_start: string;
  movie_schedule_end: string;
  tv_schedule_enabled: boolean;
  tv_schedule_hours_limited: boolean;
  tv_schedule_days: string;
  tv_schedule_start: string;
  tv_schedule_end: string;
  /** IANA id from suite settings (read-only; shared suite clock for schedule windows). */
  schedule_timezone: string;
  updated_at: string;
};

/** Partial PUT: include only fields to change (per-scope schedule saves omit the other scope). */
export type ProcessingOperatorSettingsPutBody = {
  max_concurrent_files?: number;
  runner_capacity?: number;
  runner_cost_sd?: number;
  runner_cost_720p?: number;
  runner_cost_1080p?: number;
  runner_cost_4k?: number;
  runner_cost_undetermined?: number;
  work_temp_stale_sweep_enabled?: boolean;
  failure_cleanup_enabled?: boolean;
  keep_failed_work_files?: boolean;
  file_log_retention_days?: number;
  verbose_detection_logging?: boolean;
  min_file_age_seconds?: number;
  min_input_file_size_mb?: number;
  minimum_free_disk_space_mb?: number;
  movie_schedule_enabled?: boolean;
  movie_schedule_hours_limited?: boolean;
  movie_schedule_days?: string;
  movie_schedule_start?: string;
  movie_schedule_end?: string;
  tv_schedule_enabled?: boolean;
  tv_schedule_hours_limited?: boolean;
  tv_schedule_days?: string;
  tv_schedule_start?: string;
  tv_schedule_end?: string;
};

/** POST /api/v1/processing/jobs/watched-folder-remux-scan-dispatch/enqueue */

export type ProcessingWatchedFolderRemuxScanDispatchEnqueueBody = {
  enqueue_remux_jobs: boolean;
  media_scope: "movie" | "tv";
  library_id?: number;
};

export type ProcessingWatchedFolderRemuxScanDispatchEnqueueOut = {
  ok: boolean;
  job_id: number;
  dedupe_key: string;
  job_kind: string;
};

/** POST /api/v1/processing/jobs/file-remux-pass/enqueue */

export type ProcessingFileRemuxPassManualEnqueueBody = {
  relative_media_path: string;
  media_scope: "movie" | "tv";
  library_id?: number;
  pass_through_unchanged?: boolean;
};

export type ProcessingFileRemuxPassManualEnqueueOut = {
  ok: boolean;
  job_id: number;
  dedupe_key: string;
  job_kind: string;
};
