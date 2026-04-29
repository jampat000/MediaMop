import { apiFetch, readJson, requireOk } from "../api/client";
import type { RefinerOverviewStatsOut } from "./types";

export const refinerOverviewStatsPath = () => "/api/v1/refiner/overview-stats";

export async function fetchRefinerOverviewStats(): Promise<RefinerOverviewStatsOut> {
  const path = refinerOverviewStatsPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner overview stats");
  return readJson<RefinerOverviewStatsOut>(r);
}
