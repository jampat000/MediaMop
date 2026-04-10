import { apiFetch, readJson } from "../../api/client";
import type { FailedImportTasksInspectionOut } from "./types";

export type FetchFailedImportInspectionOpts = {
  statuses?: string[];
  limit?: number;
};

export function failedImportTasksInspectionPath(opts?: FetchFailedImportInspectionOpts): string {
  const params = new URLSearchParams();
  const limit = opts?.limit ?? 50;
  params.set("limit", String(limit));
  if (opts?.statuses?.length) {
    for (const s of opts.statuses) {
      params.append("status", s);
    }
  }
  return `/api/v1/fetcher/failed-imports/inspection?${params.toString()}`;
}

export async function fetchFailedImportTasksInspection(
  opts?: FetchFailedImportInspectionOpts,
): Promise<FailedImportTasksInspectionOut> {
  const r = await apiFetch(failedImportTasksInspectionPath(opts));
  if (!r.ok) {
    throw new Error(`Could not load task list (${r.status})`);
  }
  return readJson<FailedImportTasksInspectionOut>(r);
}
