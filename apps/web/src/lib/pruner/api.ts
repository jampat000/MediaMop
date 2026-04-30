import { apiFetch, readJson, requireOk } from "../api/client";
import { fetchCsrfToken } from "../api/auth-api";

export type PrunerScopeSummary = {
  media_scope: string;
  missing_primary_media_reported_enabled: boolean;
  never_played_stale_reported_enabled: boolean;
  never_played_min_age_days: number;
  watched_tv_reported_enabled: boolean;
  watched_movies_reported_enabled: boolean;
  watched_movie_low_rating_reported_enabled: boolean;
  watched_movie_low_rating_max_jellyfin_emby_community_rating: number;
  watched_movie_low_rating_max_plex_audience_rating: number;
  unwatched_movie_stale_reported_enabled: boolean;
  unwatched_movie_stale_min_age_days: number;
  preview_max_items: number;
  preview_include_genres: string[];
  preview_include_people: string[];
  /** Credit roles used with name filters for preview narrowing; defaults to cast when absent in older clients. */
  preview_include_people_roles?: string[];
  preview_year_min: number | null;
  preview_year_max: number | null;
  preview_include_studios: string[];
  preview_include_collections: string[];
  scheduled_preview_enabled: boolean;
  scheduled_preview_interval_seconds: number;
  /** Omitted on older API responses; treat as unlimited / defaults when absent. */
  scheduled_preview_hours_limited?: boolean;
  scheduled_preview_days?: string;
  scheduled_preview_start?: string;
  scheduled_preview_end?: string;
  last_scheduled_preview_enqueued_at: string | null;
  auto_apply_enabled?: boolean;
  max_deletes_per_run?: number;
  last_preview_run_uuid: string | null;
  last_preview_at: string | null;
  last_preview_candidate_count: number | null;
  last_preview_outcome: string | null;
  last_preview_error: string | null;
};

export type PrunerOverviewStatsOut = {
  window_days: number;
  items_removed: number;
  items_skipped: number;
  apply_runs: number;
  preview_runs: number;
  failed_applies: number;
};

export type PrunerServerInstance = {
  id: number;
  provider: string;
  display_name: string;
  base_url: string;
  enabled: boolean;
  last_connection_test_at: string | null;
  last_connection_test_ok: boolean | null;
  last_connection_test_detail: string | null;
  scopes: PrunerScopeSummary[];
};

export type PrunerPreviewRun = {
  preview_run_id: string;
  server_instance_id: number;
  media_scope: string;
  rule_family_id: string;
  candidate_count: number;
  truncated: boolean;
  outcome: string;
  unsupported_detail: string | null;
  error_message: string | null;
  created_at: string;
  candidates_json: string;
};

/** Row from ``GET …/preview-runs`` (no embedded candidate JSON). */
export type PrunerApplyEligibility = {
  eligible: boolean;
  reasons: string[];
  apply_feature_enabled: boolean;
  preview_run_id: string;
  server_instance_id: number;
  media_scope: string;
  provider: string;
  display_name: string;
  preview_created_at: string | null;
  candidate_count: number;
  preview_outcome: string;
  rule_family_id: string;
  apply_operator_label: string;
};

export const RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED =
  "missing_primary_media_reported";
export const RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED =
  "never_played_stale_reported";
export const RULE_FAMILY_WATCHED_TV_REPORTED = "watched_tv_reported";
export const RULE_FAMILY_WATCHED_MOVIES_REPORTED = "watched_movies_reported";
export const RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED =
  "watched_movie_low_rating_reported";
export const RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED =
  "unwatched_movie_stale_reported";
export const RULE_FAMILY_GENRE_MATCH_REPORTED = "genre_match_reported";
export const RULE_FAMILY_STUDIO_MATCH_REPORTED = "studio_match_reported";
export const RULE_FAMILY_PEOPLE_MATCH_REPORTED = "people_match_reported";
export const RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED =
  "year_range_match_reported";

export const PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL =
  "Delete items missing a main poster or episode image";
export const PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL =
  "Delete never-started TV or movies older than your age setting";
export const PRUNER_REMOVE_WATCHED_TV_ENTRIES_LABEL =
  "Delete watched TV episodes";
export const PRUNER_REMOVE_WATCHED_MOVIES_ENTRIES_LABEL =
  "Delete watched movies";
export const PRUNER_REMOVE_WATCHED_LOW_RATING_MOVIE_ENTRIES_LABEL =
  "Delete watched movies below your score";
export const PRUNER_REMOVE_UNWATCHED_STALE_MOVIE_ENTRIES_LABEL =
  "Delete unwatched movies older than your age setting";

export function prunerApplyLabelForRuleFamily(ruleFamilyId: string): string {
  if (ruleFamilyId === RULE_FAMILY_WATCHED_TV_REPORTED) {
    return PRUNER_REMOVE_WATCHED_TV_ENTRIES_LABEL;
  }
  if (ruleFamilyId === RULE_FAMILY_WATCHED_MOVIES_REPORTED) {
    return PRUNER_REMOVE_WATCHED_MOVIES_ENTRIES_LABEL;
  }
  if (ruleFamilyId === RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED) {
    return PRUNER_REMOVE_WATCHED_LOW_RATING_MOVIE_ENTRIES_LABEL;
  }
  if (ruleFamilyId === RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED) {
    return PRUNER_REMOVE_UNWATCHED_STALE_MOVIE_ENTRIES_LABEL;
  }
  if (ruleFamilyId === RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED) {
    return PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL;
  }
  if (ruleFamilyId === RULE_FAMILY_GENRE_MATCH_REPORTED) {
    return "Remove items matching selected genres";
  }
  if (ruleFamilyId === RULE_FAMILY_STUDIO_MATCH_REPORTED) {
    return "Remove items from selected studios";
  }
  if (ruleFamilyId === RULE_FAMILY_PEOPLE_MATCH_REPORTED) {
    return "Remove items involving selected people";
  }
  if (ruleFamilyId === RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED) {
    return "Remove items from selected year range";
  }
  return PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL;
}

export type PrunerPreviewRunSummary = {
  preview_run_id: string;
  server_instance_id: number;
  media_scope: string;
  rule_family_id: string;
  pruner_job_id: number | null;
  candidate_count: number;
  truncated: boolean;
  outcome: string;
  unsupported_detail: string | null;
  error_message: string | null;
  created_at: string;
};

export type PrunerJobsInspectionRow = {
  id: number;
  dedupe_key: string;
  job_kind: string;
  status: string;
  payload_json: string | null;
  last_error: string | null;
  updated_at: string;
};

export type PrunerJobsInspectionOut = {
  jobs: PrunerJobsInspectionRow[];
  default_recent_slice: boolean;
};

export function prunerApplyEligibilityPath(
  instanceId: number,
  media_scope: "tv" | "movies",
  previewRunId: string,
): string {
  return `/api/v1/pruner/instances/${instanceId}/scopes/${media_scope}/preview-runs/${previewRunId}/apply-eligibility`;
}

export async function fetchPrunerApplyEligibility(
  instanceId: number,
  media_scope: "tv" | "movies",
  previewRunId: string,
): Promise<PrunerApplyEligibility> {
  const path = prunerApplyEligibilityPath(
    instanceId,
    media_scope,
    previewRunId,
  );
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Pruner apply eligibility");
  return readJson<PrunerApplyEligibility>(r);
}

export function prunerPreviewRunsListPath(
  instanceId: number,
  opts?: { media_scope?: "tv" | "movies"; limit?: number },
): string {
  const params = new URLSearchParams();
  if (opts?.media_scope) params.set("media_scope", opts.media_scope);
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  const q = params.toString();
  return `/api/v1/pruner/instances/${instanceId}/preview-runs${q ? `?${q}` : ""}`;
}

export async function fetchPrunerPreviewRuns(
  instanceId: number,
  opts?: { media_scope?: "tv" | "movies"; limit?: number },
): Promise<PrunerPreviewRunSummary[]> {
  const path = prunerPreviewRunsListPath(instanceId, opts);
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Pruner preview runs");
  return readJson<PrunerPreviewRunSummary[]>(r);
}

export async function fetchPrunerOverviewStats(): Promise<PrunerOverviewStatsOut> {
  const path = "/api/v1/pruner/overview-stats";
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Pruner overview stats");
  return readJson<PrunerOverviewStatsOut>(r);
}

export async function fetchPrunerInstances(): Promise<PrunerServerInstance[]> {
  const path = "/api/v1/pruner/instances";
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Pruner servers");
  return readJson<PrunerServerInstance[]>(r);
}

export async function fetchPrunerInstance(
  id: number,
): Promise<PrunerServerInstance> {
  const path = `/api/v1/pruner/instances/${id}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Pruner server");
  return readJson<PrunerServerInstance>(r);
}

export type PrunerStudiosResponse = { studios: string[] };

/** Read-only studio list for Cleanup UI; returns an empty list on any failure (never throws). */
export async function fetchPrunerStudios(
  instanceId: number,
  scope: "tv" | "movies",
): Promise<PrunerStudiosResponse> {
  try {
    const r = await apiFetch(
      `/api/v1/pruner/instances/${instanceId}/studios?scope=${encodeURIComponent(scope)}`,
    );
    if (!r.ok) {
      return { studios: [] };
    }
    return readJson<PrunerStudiosResponse>(r);
  } catch {
    return { studios: [] };
  }
}

export async function postPrunerInstance(body: {
  provider: "emby" | "jellyfin" | "plex";
  display_name: string;
  base_url: string;
  credentials: Record<string, string>;
}): Promise<PrunerServerInstance> {
  const csrf_token = await fetchCsrfToken();
  const path = "/api/v1/pruner/instances";
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not add Pruner server");
  return readJson<PrunerServerInstance>(r);
}

export async function patchPrunerInstance(
  instanceId: number,
  body: {
    display_name?: string;
    base_url?: string;
    enabled?: boolean;
    credentials?: Record<string, string>;
  },
): Promise<PrunerServerInstance> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/pruner/instances/${instanceId}`;
  const r = await apiFetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not save Pruner server");
  return readJson<PrunerServerInstance>(r);
}

export async function fetchPrunerPreviewRun(
  instanceId: number,
  previewRunId: string,
): Promise<PrunerPreviewRun> {
  const path = `/api/v1/pruner/instances/${instanceId}/preview-runs/${previewRunId}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Pruner preview");
  return readJson<PrunerPreviewRun>(r);
}

export async function postPrunerConnectionTest(
  instanceId: number,
): Promise<{ pruner_job_id: number }> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/pruner/instances/${instanceId}/connection-test`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not start Pruner connection test");
  return readJson<{ pruner_job_id: number }>(r);
}

export async function patchPrunerScope(
  instanceId: number,
  media_scope: "tv" | "movies",
  body: {
    missing_primary_media_reported_enabled?: boolean;
    never_played_stale_reported_enabled?: boolean;
    never_played_min_age_days?: number;
    watched_tv_reported_enabled?: boolean;
    watched_movies_reported_enabled?: boolean;
    watched_movie_low_rating_reported_enabled?: boolean;
    watched_movie_low_rating_max_jellyfin_emby_community_rating?: number;
    watched_movie_low_rating_max_plex_audience_rating?: number;
    unwatched_movie_stale_reported_enabled?: boolean;
    unwatched_movie_stale_min_age_days?: number;
    preview_max_items?: number;
    preview_include_genres?: string[];
    preview_include_people?: string[];
    preview_include_people_roles?: string[];
    preview_year_min?: number | null;
    preview_year_max?: number | null;
    preview_include_studios?: string[];
    preview_include_collections?: string[];
    scheduled_preview_enabled?: boolean;
    scheduled_preview_interval_seconds?: number;
    scheduled_preview_hours_limited?: boolean;
    scheduled_preview_days?: string;
    scheduled_preview_start?: string;
    scheduled_preview_end?: string;
    auto_apply_enabled?: boolean;
    max_deletes_per_run?: number;
    csrf_token: string;
  },
): Promise<PrunerScopeSummary> {
  const path = `/api/v1/pruner/instances/${instanceId}/scopes/${media_scope}`;
  const r = await apiFetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await requireOk(path, r, "Could not save Pruner cleanup scope");
  return readJson<PrunerScopeSummary>(r);
}

export async function postPrunerApplyFromPreview(
  instanceId: number,
  media_scope: "tv" | "movies",
  previewRunId: string,
): Promise<{ pruner_job_id: number }> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/pruner/instances/${instanceId}/scopes/${media_scope}/preview-runs/${previewRunId}/apply`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not apply Pruner cleanup");
  return readJson<{ pruner_job_id: number }>(r);
}

export async function postPrunerPreview(
  instanceId: number,
  media_scope: "tv" | "movies",
  opts?: { rule_family_id?: string },
): Promise<{ pruner_job_id: number }> {
  const csrf_token = await fetchCsrfToken();
  const payload: Record<string, string> = { media_scope, csrf_token };
  if (opts?.rule_family_id) {
    payload.rule_family_id = opts.rule_family_id;
  }
  const path = `/api/v1/pruner/instances/${instanceId}/previews`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await requireOk(path, r, "Could not start Pruner cleanup preview");
  return readJson<{ pruner_job_id: number }>(r);
}

export async function fetchPrunerJobsInspection(
  limit = 50,
): Promise<PrunerJobsInspectionOut> {
  const params = new URLSearchParams({ limit: String(limit) });
  const path = `/api/v1/pruner/jobs/inspection?${params.toString()}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Pruner jobs");
  return readJson<PrunerJobsInspectionOut>(r);
}
