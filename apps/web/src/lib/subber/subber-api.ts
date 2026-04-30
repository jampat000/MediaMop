import { apiFetch, readJson, requireOk } from "../api/client";
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

export type SubberMoviesLibraryOut = {
  movies: SubberMovieRow[];
  total: number;
};

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
  arr_library_sonarr_base_url_hint: string;
  arr_library_radarr_base_url_hint: string;
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

export type SubberArrRootFolderOut = {
  path: string;
  free_space: number | null;
};

export type SubberArrRootFoldersOut = {
  ok: boolean;
  message: string;
  folders: SubberArrRootFolderOut[];
};

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
  priority: number | null;
  requires_account: boolean;
  has_credentials: boolean;
  available: boolean;
  availability_note: string | null;
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

export type SubberJobsInspectionOut = {
  jobs: SubberJobsInspectionRow[];
  default_recent_slice: boolean;
};

export async function fetchSubberSettings(): Promise<SubberSettingsOut> {
  const path = "/api/v1/subber/settings";
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Subber settings");
  return readJson<SubberSettingsOut>(r);
}

export async function putSubberSettings(
  body: SubberSettingsPutIn,
): Promise<SubberSettingsOut> {
  const path = "/api/v1/subber/settings";
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await requireOk(path, r, "Could not save Subber settings");
  return readJson<SubberSettingsOut>(r);
}

export async function postSubberTestOpensubtitles(): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/settings/test-opensubtitles";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not test OpenSubtitles");
  return readJson<SubberTestConnectionOut>(r);
}

export async function postSubberTestSonarr(): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/settings/test-sonarr";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not test Sonarr");
  return readJson<SubberTestConnectionOut>(r);
}

export async function postSubberTestRadarr(): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/settings/test-radarr";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not test Radarr");
  return readJson<SubberTestConnectionOut>(r);
}

export async function postSubberSonarrRootFolders(): Promise<SubberArrRootFoldersOut> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/settings/sonarr-root-folders";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not load Sonarr root folders");
  return readJson<SubberArrRootFoldersOut>(r);
}

export async function postSubberRadarrRootFolders(): Promise<SubberArrRootFoldersOut> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/settings/radarr-root-folders";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not load Radarr root folders");
  return readJson<SubberArrRootFoldersOut>(r);
}

export async function fetchSubberOverview(): Promise<SubberOverviewOut> {
  const path = "/api/v1/subber/overview";
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Subber overview");
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
  const path = `/api/v1/subber/library/tv${qs ? `?${qs}` : ""}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load TV subtitle library");
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
  const path = `/api/v1/subber/library/movies${qs ? `?${qs}` : ""}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load movie subtitle library");
  return readJson<SubberMoviesLibraryOut>(r);
}

export async function postSubberSearchNow(
  stateId: number,
): Promise<{ status: string }> {
  const csrf = await fetchCsrfToken();
  const path = `/api/v1/subber/library/${stateId}/search-now`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not start subtitle search");
  return readJson(r);
}

export async function postSubberSearchAllMissingTv(): Promise<{
  status: string;
}> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/library/search-all-missing/tv";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not start TV subtitle search");
  return readJson(r);
}

export async function postSubberSearchAllMissingMovies(): Promise<{
  status: string;
}> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/library/search-all-missing/movies";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not start movie subtitle search");
  return readJson(r);
}

export async function postSubberLibrarySyncTv(): Promise<{ status: string }> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/library/sync/tv";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not sync TV library");
  return readJson(r);
}

export async function postSubberLibrarySyncMovies(): Promise<{
  status: string;
}> {
  const csrf = await fetchCsrfToken();
  const path = "/api/v1/subber/library/sync/movies";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not sync movie library");
  return readJson(r);
}

export async function fetchSubberProviders(): Promise<SubberProviderOut[]> {
  const path = "/api/v1/subber/providers";
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load subtitle providers");
  return readJson<SubberProviderOut[]>(r);
}

export async function putSubberProvider(
  providerKey: string,
  body: SubberProviderPutIn,
): Promise<SubberProviderOut> {
  const pk = encodeURIComponent(providerKey);
  const path = `/api/v1/subber/providers/${pk}`;
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await requireOk(path, r, "Could not save subtitle provider");
  return readJson<SubberProviderOut>(r);
}

export async function postSubberProviderTest(
  providerKey: string,
): Promise<SubberTestConnectionOut> {
  const csrf = await fetchCsrfToken();
  const pk = encodeURIComponent(providerKey);
  const path = `/api/v1/subber/providers/${pk}/test`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token: csrf }),
  });
  await requireOk(path, r, "Could not test subtitle provider");
  return readJson<SubberTestConnectionOut>(r);
}

export async function fetchSubberJobs(
  limit = 50,
): Promise<SubberJobsInspectionOut> {
  const path = `/api/v1/subber/jobs?limit=${encodeURIComponent(String(limit))}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Subber jobs");
  return readJson<SubberJobsInspectionOut>(r);
}
