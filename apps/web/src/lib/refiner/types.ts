/** GET/PUT /api/v1/refiner/path-settings — Refiner watched / work / output folders (singleton row). */

export type RefinerPathSettingsOut = {
  refiner_watched_folder: string | null;
  refiner_watched_folder_exists: boolean;
  refiner_work_folder: string | null;
  refiner_output_folder: string | null;
  resolved_default_work_folder: string;
  effective_work_folder: string;
  refiner_tv_watched_folder: string | null;
  refiner_tv_watched_folder_exists: boolean;
  refiner_tv_work_folder: string | null;
  refiner_tv_output_folder: string | null;
  resolved_default_tv_work_folder: string;
  effective_tv_work_folder: string;
  /** How often the server re-evaluates periodic Movies scans vs this library (10–604800 seconds). */
  movie_watched_folder_check_interval_seconds: number;
  /** How often the server re-evaluates periodic TV scans vs this library (10–604800 seconds). */
  tv_watched_folder_check_interval_seconds: number;
  updated_at: string;
};

export type RefinerPathSettingsPutBody = {
  refiner_watched_folder: string | null;
  refiner_work_folder: string | null;
  refiner_output_folder: string | null;
  /** When true, TV path fields are written (send empty strings to clear TV paths). */
  refiner_tv_paths_included: boolean;
  refiner_tv_watched_folder: string | null;
  refiner_tv_work_folder: string | null;
  refiner_tv_output_folder: string | null;
  /** Send current Movies value on every save (Movies or TV card). */
  movie_watched_folder_check_interval_seconds: number;
  /** Send current TV value on every save (Movies or TV card). */
  tv_watched_folder_check_interval_seconds: number;
};

/** GET /api/v1/refiner/runtime-settings — read-only Refiner in-process worker snapshot. */

export type RefinerRuntimeSettingsOut = {
  in_process_refiner_worker_count: number;
  in_process_workers_disabled: boolean;
  in_process_workers_enabled: boolean;
  worker_mode_summary: string;
  sqlite_throughput_note: string;
  configuration_note: string;
  visibility_note: string;
  refiner_watched_folder_remux_scan_dispatch_schedule_enabled: boolean;
  refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds: number;
  refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs: boolean;
  refiner_watched_folder_min_file_age_seconds: number;
  refiner_movie_output_cleanup_min_age_seconds: number;
  movie_output_cleanup_configuration_note: string;
  refiner_tv_output_cleanup_min_age_seconds: number;
  tv_output_cleanup_configuration_note: string;
  watched_folder_scan_periodic_configuration_note: string;
  refiner_work_temp_stale_sweep_movie_schedule_enabled: boolean;
  refiner_work_temp_stale_sweep_movie_schedule_interval_seconds: number;
  refiner_work_temp_stale_sweep_tv_schedule_enabled: boolean;
  refiner_work_temp_stale_sweep_tv_schedule_interval_seconds: number;
  refiner_work_temp_stale_sweep_min_stale_age_seconds: number;
  refiner_movie_failure_cleanup_schedule_enabled: boolean;
  refiner_movie_failure_cleanup_schedule_interval_seconds: number;
  refiner_tv_failure_cleanup_schedule_enabled: boolean;
  refiner_tv_failure_cleanup_schedule_interval_seconds: number;
  refiner_movie_failure_cleanup_grace_period_seconds: number;
  refiner_tv_failure_cleanup_grace_period_seconds: number;
  failure_cleanup_configuration_note: string;
  work_temp_stale_sweep_periodic_configuration_note: string;
};

export type RefinerOverviewStatsOut = {
  window_days: number;
  files_processed: number;
  files_failed: number;
  success_rate_percent: number;
  output_written_count: number;
  already_optimized_count: number;
  net_space_saved_bytes: number;
  net_space_saved_percent: number;
};

export type RefinerOperatorSettingsOut = {
  max_concurrent_files: number;
  min_file_age_seconds: number;
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
export type RefinerOperatorSettingsPutBody = {
  max_concurrent_files?: number;
  min_file_age_seconds?: number;
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

/** POST /api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue */

export type RefinerWatchedFolderRemuxScanDispatchEnqueueBody = {
  enqueue_remux_jobs: boolean;
  media_scope: "movie" | "tv";
};

export type RefinerWatchedFolderRemuxScanDispatchEnqueueOut = {
  ok: boolean;
  job_id: number;
  dedupe_key: string;
  job_kind: string;
};

/** GET/PUT /api/v1/refiner/remux-rules-settings */

export type RefinerRemuxRulesSettingsOut = {
  movie: RefinerRemuxRulesScopeSettings;
  tv: RefinerRemuxRulesScopeSettings;
  updated_at: string;
};

export type RefinerRemuxRulesScopeSettings = {
  primary_audio_lang: string;
  secondary_audio_lang: string;
  tertiary_audio_lang: string;
  default_audio_slot: "primary" | "secondary";
  remove_commentary: boolean;
  subtitle_mode: "remove_all" | "keep_selected";
  subtitle_langs_csv: string;
  preserve_forced_subs: boolean;
  preserve_default_subs: boolean;
  audio_preference_mode: "preferred_langs_quality" | "preferred_langs_strict" | "quality_all_languages";
};

export type RefinerRemuxRulesSettingsPutBody = RefinerRemuxRulesScopeSettings & {
  media_scope: "movie" | "tv";
};

/** POST /api/v1/refiner/jobs/file-remux-pass/enqueue */

export type RefinerFileRemuxPassManualEnqueueBody = {
  relative_media_path: string;
  media_scope: "movie" | "tv";
};

export type RefinerFileRemuxPassManualEnqueueOut = {
  ok: boolean;
  job_id: number;
  dedupe_key: string;
  job_kind: string;
};
