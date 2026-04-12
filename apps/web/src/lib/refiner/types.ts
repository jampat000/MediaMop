/** GET/PUT /api/v1/refiner/path-settings — Refiner watched / work / output folders (singleton row). */

export type RefinerPathSettingsOut = {
  refiner_watched_folder: string | null;
  refiner_work_folder: string | null;
  refiner_output_folder: string;
  resolved_default_work_folder: string;
  effective_work_folder: string;
  updated_at: string;
};

export type RefinerPathSettingsPutBody = {
  refiner_watched_folder: string | null;
  refiner_work_folder: string | null;
  refiner_output_folder: string;
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
};
