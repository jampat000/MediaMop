import { apiFetch, readJson, requireOk } from "../api/client";
import type { ProcessingOverviewStatsOut } from "./types";

export const processingOverviewStatsPath = () =>
  "/api/v1/processing/overview-stats";

export async function fetchProcessingOverviewStats(
  windowDays?: number,
): Promise<ProcessingOverviewStatsOut> {
  const path =
    windowDays === undefined
      ? processingOverviewStatsPath()
      : `${processingOverviewStatsPath()}?window_days=${windowDays}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load processing stats");
  return readJson<ProcessingOverviewStatsOut>(r);
}
