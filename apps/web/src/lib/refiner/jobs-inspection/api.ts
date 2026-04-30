import { fetchCsrfToken } from "../../api/auth-api";
import { apiFetch, readJson, requireOk } from "../../api/client";
import type {
  RefinerJobCancelPendingOut,
  RefinerJobsInspectionOut,
} from "./types";

export type FetchRefinerJobsInspectionOpts = {
  statuses?: string[];
  limit?: number;
};

export function refinerJobsInspectionPath(
  opts?: FetchRefinerJobsInspectionOpts,
): string {
  const params = new URLSearchParams();
  const limit = opts?.limit ?? 100;
  params.set("limit", String(limit));
  if (opts?.statuses?.length) {
    for (const s of opts.statuses) {
      params.append("status", s);
    }
  }
  return `/api/v1/refiner/jobs/inspection?${params.toString()}`;
}

export async function fetchRefinerJobsInspection(
  opts?: FetchRefinerJobsInspectionOpts,
): Promise<RefinerJobsInspectionOut> {
  const path = refinerJobsInspectionPath(opts);
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner jobs");
  return readJson<RefinerJobsInspectionOut>(r);
}

export async function postRefinerJobCancelPending(
  jobId: number,
): Promise<RefinerJobCancelPendingOut> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/refiner/jobs/${jobId}/cancel-pending`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not cancel Refiner job");
  return readJson<RefinerJobCancelPendingOut>(r);
}
