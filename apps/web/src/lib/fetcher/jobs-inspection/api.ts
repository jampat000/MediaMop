import { apiFetch, readJson } from "../../api/client";
import type { FetcherJobsInspectionOut } from "./types";

export type FetchFetcherJobsInspectionOpts = {
  statuses?: string[];
  limit?: number;
};

export function fetcherJobsInspectionPath(opts?: FetchFetcherJobsInspectionOpts): string {
  const params = new URLSearchParams();
  const limit = opts?.limit ?? 50;
  params.set("limit", String(limit));
  if (opts?.statuses?.length) {
    for (const s of opts.statuses) {
      params.append("status", s);
    }
  }
  return `/api/v1/fetcher/jobs/inspection?${params.toString()}`;
}

export async function fetchFetcherJobsInspection(
  opts?: FetchFetcherJobsInspectionOpts,
): Promise<FetcherJobsInspectionOut> {
  const r = await apiFetch(fetcherJobsInspectionPath(opts));
  if (!r.ok) {
    throw new Error(`Could not load Fetcher jobs (${r.status})`);
  }
  return readJson<FetcherJobsInspectionOut>(r);
}
