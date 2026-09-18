/** Shapes for ``GET /api/v1/processing/jobs/inspection`` (Processing lane only). */

export type ProcessingJobInspectionRow = {
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

export type ProcessingJobsInspectionOut = {
  jobs: ProcessingJobInspectionRow[];
  default_recent_slice: boolean;
};

export type ProcessingJobCancelPendingOut = {
  ok: boolean;
  job_id: number;
  status: string;
};

export type ProcessingJobRecoverFinalizeFailedOut = {
  ok: boolean;
  job_id: number;
  status: string;
};
