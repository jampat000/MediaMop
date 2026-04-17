import { apiFetch, apiErrorDetailToString, readJson } from "../api/client";
import { fetchCsrfToken } from "../api/auth-api";

export type PrunerScopeSummary = {
  media_scope: string;
  missing_primary_media_reported_enabled: boolean;
  never_played_stale_reported_enabled: boolean;
  never_played_min_age_days: number;
  watched_tv_reported_enabled: boolean;
  watched_movies_reported_enabled: boolean;
  preview_max_items: number;
  preview_include_genres: string[];
  preview_include_people: string[];
  scheduled_preview_enabled: boolean;
  scheduled_preview_interval_seconds: number;
  last_scheduled_preview_enqueued_at: string | null;
  last_preview_run_uuid: string | null;
  last_preview_at: string | null;
  last_preview_candidate_count: number | null;
  last_preview_outcome: string | null;
  last_preview_error: string | null;
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

export const RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED = "missing_primary_media_reported";
export const RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED = "never_played_stale_reported";
export const RULE_FAMILY_WATCHED_TV_REPORTED = "watched_tv_reported";
export const RULE_FAMILY_WATCHED_MOVIES_REPORTED = "watched_movies_reported";

export const PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL = "Remove broken library entries";
export const PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL = "Remove stale never-played library entries";
export const PRUNER_REMOVE_WATCHED_TV_ENTRIES_LABEL = "Remove watched TV entries";
export const PRUNER_REMOVE_WATCHED_MOVIES_ENTRIES_LABEL = "Remove watched movie entries";

export function prunerApplyLabelForRuleFamily(ruleFamilyId: string): string {
  if (ruleFamilyId === RULE_FAMILY_WATCHED_TV_REPORTED) {
    return PRUNER_REMOVE_WATCHED_TV_ENTRIES_LABEL;
  }
  if (ruleFamilyId === RULE_FAMILY_WATCHED_MOVIES_REPORTED) {
    return PRUNER_REMOVE_WATCHED_MOVIES_ENTRIES_LABEL;
  }
  if (ruleFamilyId === RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED) {
    return PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL;
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
  const r = await apiFetch(prunerApplyEligibilityPath(instanceId, media_scope, previewRunId));
  if (!r.ok) {
    throw new Error(`Pruner apply eligibility: ${r.status}`);
  }
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
  const r = await apiFetch(prunerPreviewRunsListPath(instanceId, opts));
  if (!r.ok) {
    throw new Error(`Pruner preview runs: ${r.status}`);
  }
  return readJson<PrunerPreviewRunSummary[]>(r);
}

export async function fetchPrunerInstances(): Promise<PrunerServerInstance[]> {
  const r = await apiFetch("/api/v1/pruner/instances");
  if (!r.ok) {
    throw new Error(`Pruner instances: ${r.status}`);
  }
  return readJson<PrunerServerInstance[]>(r);
}

export async function fetchPrunerInstance(id: number): Promise<PrunerServerInstance> {
  const r = await apiFetch(`/api/v1/pruner/instances/${id}`);
  if (!r.ok) {
    throw new Error(`Pruner instance: ${r.status}`);
  }
  return readJson<PrunerServerInstance>(r);
}

export async function fetchPrunerPreviewRun(
  instanceId: number,
  previewRunId: string,
): Promise<PrunerPreviewRun> {
  const r = await apiFetch(`/api/v1/pruner/instances/${instanceId}/preview-runs/${previewRunId}`);
  if (!r.ok) {
    throw new Error(`Pruner preview run: ${r.status}`);
  }
  return readJson<PrunerPreviewRun>(r);
}

export async function postPrunerConnectionTest(instanceId: number): Promise<{ pruner_job_id: number }> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(`/api/v1/pruner/instances/${instanceId}/connection-test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  if (!r.ok) {
    const body = (await readJson<{ detail?: unknown }>(r).catch(() => ({}))) as { detail?: unknown };
    throw new Error(apiErrorDetailToString(body.detail) || `connection test: ${r.status}`);
  }
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
    preview_max_items?: number;
    preview_include_genres?: string[];
    preview_include_people?: string[];
    scheduled_preview_enabled?: boolean;
    scheduled_preview_interval_seconds?: number;
    csrf_token: string;
  },
): Promise<PrunerScopeSummary> {
  const r = await apiFetch(`/api/v1/pruner/instances/${instanceId}/scopes/${media_scope}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const errBody = (await readJson<{ detail?: unknown }>(r).catch(() => ({}))) as { detail?: unknown };
    throw new Error(apiErrorDetailToString(errBody.detail) || `Pruner scope: ${r.status}`);
  }
  return readJson<PrunerScopeSummary>(r);
}

export async function postPrunerApplyFromPreview(
  instanceId: number,
  media_scope: "tv" | "movies",
  previewRunId: string,
): Promise<{ pruner_job_id: number }> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(
    `/api/v1/pruner/instances/${instanceId}/scopes/${media_scope}/preview-runs/${previewRunId}/apply`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csrf_token }),
    },
  );
  if (!r.ok) {
    const body = (await readJson<{ detail?: unknown }>(r).catch(() => ({}))) as { detail?: unknown };
    throw new Error(apiErrorDetailToString(body.detail) || `apply: ${r.status}`);
  }
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
  const r = await apiFetch(`/api/v1/pruner/instances/${instanceId}/previews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const body = (await readJson<{ detail?: unknown }>(r).catch(() => ({}))) as { detail?: unknown };
    throw new Error(apiErrorDetailToString(body.detail) || `preview: ${r.status}`);
  }
  return readJson<{ pruner_job_id: number }>(r);
}
