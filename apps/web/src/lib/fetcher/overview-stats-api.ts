import { apiFetch, readJson } from "../api/client";

export type FetcherOverviewStatsOut = {
  window_days: number;
  sonarr_missing_searches: number;
  sonarr_upgrade_searches: number;
  radarr_missing_searches: number;
  radarr_upgrade_searches: number;
  total_searches: number;
  failed_jobs: number;
};

export async function fetchFetcherOverviewStats(): Promise<FetcherOverviewStatsOut> {
  const r = await apiFetch("/api/v1/fetcher/overview-stats");
  if (!r.ok) {
    throw new Error(`Could not load Fetcher overview stats (${r.status})`);
  }
  return readJson<FetcherOverviewStatsOut>(r);
}
