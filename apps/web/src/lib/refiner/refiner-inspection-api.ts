import { apiFetch, readJson } from "../api/client";
import type { RefinerJobsInspectionOut } from "./types";

export type FetchRefinerInspectionOpts = {
  /** Omit or empty: backend default (terminal rows only). */
  statuses?: string[];
  limit?: number;
};

/** Relative path under ``/api/v1`` for tests and single place for query shape. */
export function refinerJobsInspectionPath(opts?: FetchRefinerInspectionOpts): string {
  const params = new URLSearchParams();
  const limit = opts?.limit ?? 50;
  params.set("limit", String(limit));
  if (opts?.statuses?.length) {
    for (const s of opts.statuses) {
      params.append("status", s);
    }
  }
  return `/api/v1/refiner/jobs/inspection?${params.toString()}`;
}

export async function fetchRefinerJobsInspection(
  opts?: FetchRefinerInspectionOpts,
): Promise<RefinerJobsInspectionOut> {
  const r = await apiFetch(refinerJobsInspectionPath(opts));
  if (!r.ok) {
    throw new Error(`refiner jobs inspection: ${r.status}`);
  }
  return readJson<RefinerJobsInspectionOut>(r);
}
