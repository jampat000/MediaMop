import { apiFetch, readJson, requireOk } from "../api/client";
import type { RefinerOverviewStatsOut } from "./types";

export const refinerOverviewStatsPath = () => "/api/v1/refiner/overview-stats";

export async function fetchRefinerOverviewStats(
  windowDays?: number,
): Promise<RefinerOverviewStatsOut> {
  const path =
    windowDays === undefined
      ? refinerOverviewStatsPath()
      : `${refinerOverviewStatsPath()}?window_days=${windowDays}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner overview stats");
  return readJson<RefinerOverviewStatsOut>(r);
}
