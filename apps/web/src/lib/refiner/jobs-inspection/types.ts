/** Shapes for ``GET /api/v1/refiner/jobs/inspection`` (Refiner lane only). */

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
  operator_message?: string;
  next_action?: string;
  technical_detail?: string | null;
  payload_json: string | null;
  created_at: string;
  updated_at: string;
};

export type RefinerJobsInspectionOut = {
  jobs: RefinerJobInspectionRow[];
  default_recent_slice: boolean;
};

export type RefinerJobCancelPendingOut = {
  ok: boolean;
  job_id: number;
  status: string;
};

export type RefinerJobRecoverFinalizeFailedOut = {
  ok: boolean;
  job_id: number;
  status: string;
};
