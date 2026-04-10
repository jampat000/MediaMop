/** Shapes for ``GET /api/v1/refiner/jobs/inspection`` (Pass 19). */

export type RefinerJobInspectionRow = {
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

export type RefinerJobsInspectionOut = {
  jobs: RefinerJobInspectionRow[];
  default_terminal_only: boolean;
};

/** ``GET /api/v1/refiner/runtime/visibility`` (Pass 22) — settings intent, not liveness. */

export type RefinerRuntimeVisibilityOut = {
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
