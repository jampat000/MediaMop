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
