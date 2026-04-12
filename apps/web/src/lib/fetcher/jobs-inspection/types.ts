/** Shapes for ``GET /api/v1/fetcher/jobs/inspection`` (all Fetcher lane job kinds). */

export type FetcherJobInspectionRow = {
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

export type FetcherJobsInspectionOut = {
  jobs: FetcherJobInspectionRow[];
  default_terminal_only: boolean;
};
