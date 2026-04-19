import { apiErrorDetailToString, apiFetch, readJson } from "../api/client";
import { fetchCsrfToken } from "../api/auth-api";

export type SubberSubtitleLangState = {
  state_id: number;
  language_code: string;
  status: string;
  subtitle_path: string | null;
  last_searched_at: string | null;
  search_count: number;
  source: string | null;
  provider_key?: string | null;
  upgrade_count?: number;
};

export type SubberTvEpisode = {
  file_path: string;
  episode_number: number | null;
  episode_title: string | null;
  languages: SubberSubtitleLangState[];
};

export type SubberTvSeason = {
  season_number: number | null;
  episodes: SubberTvEpisode[];
};

export type SubberTvShow = {
  show_title: string;
  seasons: SubberTvSeason[];
};

export type SubberTvLibraryOut = { shows: SubberTvShow[]; total: number };

export type SubberMovieRow = {
  file_path: string;
  movie_title: string | null;
  movie_year: number | null;
  languages: SubberSubtitleLangState[];
};

export type SubberMoviesLibraryOut = { movies: SubberMovieRow[]; total: number };

/** Flat JSON from GET/PUT ``/api/v1/subber/settings``; field groups mirror ``subber_settings_schema_sections`` on the server and the Subber Settings tab UI. */
export type SubberSettingsOut = {
  enabled: boolean;
  opensubtitles_username: string;
  opensubtitles_password_set: boolean;
  opensubtitles_api_key_set: boolean;
  sonarr_base_url: string;
  sonarr_api_key_set: boolean;
  radarr_base_url: string;
  radarr_api_key_set: boolean;
  language_preferences: string[];
  subtitle_folder: string;
  tv_schedule_enabled: boolean;
  tv_schedule_interval_seconds: number;
  tv_schedule_hours_limited: boolean;
  tv_schedule_days: string;
  tv_schedule_start: string;
  tv_schedule_end: string;
  movies_schedule_enabled: boolean;
  movies_schedule_interval_seconds: number;
  movies_schedule_hours_limited: boolean;
  movies_schedule_days: string;
  movies_schedule_start: string;
  movies_schedule_end: string;
  tv_last_scheduled_scan_enqueued_at: string | null;
  movies_last_scheduled_scan_enqueued_at: string | null;
  adaptive_searching_enabled: boolean;
  adaptive_searching_delay_hours: number;
  adaptive_searching_max_attempts: number;
  permanent_skip_after_attempts: number;
  exclude_hearing_impaired: boolean;
  upgrade_enabled: boolean;
  upgrade_schedule_enabled: boolean;
  upgrade_schedule_interval_seconds: number;
  upgrade_schedule_hours_limited: boolean;
  upgrade_schedule_days: string;
  upgrade_schedule_start: string;
  upgrade_schedule_end: string;
  upgrade_last_scheduled_at: string | null;
  sonarr_path_mapping_enabled: boolean;
  sonarr_path_sonarr: string;
  sonarr_path_subber: string;
  radarr_path_mapping_enabled: boolean;
  radarr_path_radarr: string;
  radarr_path_subber: string;
  fetcher_sonarr_base_url_hint: string;
  fetcher_radarr_base_url_hint: string;
};

/** Partial update body; same flat keys as ``SubberSettingsOut`` where applicable. */
export type SubberSettingsPutIn = {
  csrf_token: string;
  enabled?: boolean;
  opensubtitles_username?: string;
  opensubtitles_password?: string;
  opensubtitles_api_key?: string;
  sonarr_base_url?: string;
  sonarr_api_key?: string;
  radarr_base_url?: string;
  radarr_api_key?: string;
  language_preferences?: string[];
  subtitle_folder?: string;
  tv_schedule_enabled?: boolean;
  tv_schedule_interval_seconds?: number;
  tv_schedule_hours_limited?: boolean;
  tv_schedule_days?: string;
  tv_schedule_start?: string;
  tv_schedule_end?: string;
  movies_schedule_enabled?: boolean;
  movies_schedule_interval_seconds?: number;
  movies_schedule_hours_limited?: boolean;
  movies_schedule_days?: string;
  movies_schedule_start?: string;
  movies_schedule_end?: string;
  adaptive_searching_enabled?: boolean;
  adaptive_searching_delay_hours?: number;
  adaptive_searching_max_attempts?: number;
  permanent_skip_after_attempts?: number;
  exclude_hearing_impaired?: boolean;
  upgrade_enabled?: boolean;
  upgrade_schedule_enabled?: boolean;
  upgrade_schedule_interval_seconds?: number;
  upgrade_schedule_hours_limited?: boolean;
  upgrade_schedule_days?: string;
  upgrade_schedule_start?: string;
  upgrade_schedule_end?: string;
  sonarr_path_mapping_enabled?: boolean;
  sonarr_path_sonarr?: string;
  sonarr_path_subber?: string;
  radarr_path_mapping_enabled?: boolean;
  radarr_path_radarr?: string;
  radarr_path_subber?: string;
};

export type SubberTestConnectionOut = { ok: boolean; message: string };

export type SubberOverviewOut = {
  window_days: number;
  subtitles_downloaded: number;
  still_missing: number;
  skipped: number;
  tv_tracked: number;
  movies_tracked: number;
  tv_found: number;
  movies_found: number;
  tv_missing: number;
  movies_missing: number;
  searches_last_30_days: number;
  found_last_30_days: number;
  not_found_last_30_days: number;
  upgrades_last_30_days: number;
};

export type SubberProviderOut = {
  provider_key: string;
  display_name: string;
  enabled: boolean;
  priority: number;
  requires_account: boolean;
  has_credentials: boolean;
};

export type SubberProviderPutIn = {
  csrf_token: string;
  enabled?: boolean;
  priority?: number;
  username?: string;
  password?: string;
  api_key?: string;
};

export type SubberJobsInspectionRow = {
  id: number;
  dedupe_key: string;
  job_kind: string;
  status: string;
  scope: string | null;
  payload_json: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export type SubberJobsInspectionOut = { jobs: SubberJobsInspectionRow[]; default_recent_slice: boolean };

export async function fetchSubberSettings(): Promise<SubberSettingsOut> {
  const r = await apiFetch("/api/v1/subber/settings");
  if (!r.ok) throw new Error(`Subber settings: ${r.status}`);
  return readJson<SubberSettingsOut>(r);
}

export async function putSubberSettings(body: SubberSettingsPutIn): Promise<SubberSettingsOut> {
  const r = await apiFetch("/api/v1/subber/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`Subber settings save: ${r.status}`);
  return readJson<SubberSettingsOut>(r);
}

export async function postSubberTestOpensubtitles(): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/subber/settings/test-opensubtitles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) throw new Error(`OpenSubtitles test: ${r.status}`);
  return readJson<SubberTestConnectionOut>(r);
}

export async function postSubberTestSonarr(): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/subber/settings/test-sonarr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) throw new Error(`Sonarr test: ${r.status}`);
  return readJson<SubberTestConnectionOut>(r);
}

export async function postSubberTestRadarr(): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/subber/settings/test-radarr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) throw new Error(`Radarr test: ${r.status}`);
  return readJson<SubberTestConnectionOut>(r);
}

export async function fetchSubberOverview(): Promise<SubberOverviewOut> {
  const r = await apiFetch("/api/v1/subber/overview");
  if (!r.ok) throw new Error(`Subber overview: ${r.status}`);
  return readJson<SubberOverviewOut>(r);
}

export async function fetchSubberLibraryTv(params: {
  status?: string;
  search?: string;
  language?: string;
  limit?: number;
  offset?: number;
}): Promise<SubberTvLibraryOut> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.search) q.set("search", params.search);
  if (params.language) q.set("language", params.language);
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  const qs = q.toString();
  const r = await apiFetch(`/api/v1/subber/library/tv${qs ? `?${qs}` : ""}`);
  if (!r.ok) throw new Error(`Subber TV library: ${r.status}`);
  return readJson<SubberTvLibraryOut>(r);
}

export async function fetchSubberLibraryMovies(params: {
  status?: string;
  search?: string;
  language?: string;
  limit?: number;
  offset?: number;
}): Promise<SubberMoviesLibraryOut> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.search) q.set("search", params.search);
  if (params.language) q.set("language", params.language);
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  const qs = q.toString();
  const r = await apiFetch(`/api/v1/subber/library/movies${qs ? `?${qs}` : ""}`);
  if (!r.ok) throw new Error(`Subber movies library: ${r.status}`);
  return readJson<SubberMoviesLibraryOut>(r);
}

export async function postSubberSearchNow(stateId: number): Promise<{ status: string }> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch(`/api/v1/subber/library/${stateId}/search-now`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) throw new Error(`Subber search now: ${r.status}`);
  return readJson(r);
}

export async function postSubberSearchAllMissingTv(): Promise<{ status: string }> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/subber/library/search-all-missing/tv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) throw new Error(`Subber search all TV: ${r.status}`);
  return readJson(r);
}

export async function postSubberSearchAllMissingMovies(): Promise<{ status: string }> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/subber/library/search-all-missing/movies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) throw new Error(`Subber search all movies: ${r.status}`);
  return readJson(r);
}

export async function postSubberLibrarySyncTv(): Promise<{ status: string }> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/subber/library/sync/tv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) {
    let msg = `TV library sync failed (${r.status}).`;
    try {
      const body = await readJson<{ detail?: unknown }>(r);
      const d = apiErrorDetailToString(body.detail);
      if (d) msg = r.status === 404 ? `${d} — restart the API from the current repo so this route is registered.` : d;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return readJson(r);
}

export async function postSubberLibrarySyncMovies(): Promise<{ status: string }> {
  const csrf = await fetchCsrfToken();
  const r = await apiFetch("/api/v1/subber/library/sync/movies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) {
    let msg = `Movies library sync failed (${r.status}).`;
    try {
      const body = await readJson<{ detail?: unknown }>(r);
      const d = apiErrorDetailToString(body.detail);
      if (d) msg = r.status === 404 ? `${d} — restart the API from the current repo so this route is registered.` : d;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return readJson(r);
}

export async function fetchSubberProviders(): Promise<SubberProviderOut[]> {
  const r = await apiFetch("/api/v1/subber/providers");
  if (!r.ok) throw new Error(`Subber providers: ${r.status}`);
  return readJson<SubberProviderOut[]>(r);
}

export async function putSubberProvider(providerKey: string, body: SubberProviderPutIn): Promise<SubberProviderOut> {
  const pk = encodeURIComponent(providerKey);
  const r = await apiFetch(`/api/v1/subber/providers/${pk}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`Subber provider save: ${r.status}`);
  return readJson<SubberProviderOut>(r);
}

export async function postSubberProviderTest(providerKey: string): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const pk = encodeURIComponent(providerKey);
  const r = await apiFetch(`/api/v1/subber/providers/${pk}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  if (!r.ok) throw new Error(`Subber provider test: ${r.status}`);
  return readJson<SubberTestConnectionOut>(r);
}

export async function fetchSubberJobs(limit = 50): Promise<SubberJobsInspectionOut> {
  const r = await apiFetch(`/api/v1/subber/jobs?limit=${encodeURIComponent(String(limit))}`);
  if (!r.ok) throw new Error(`Subber jobs: ${r.status}`);
  return readJson<SubberJobsInspectionOut>(r);
}
