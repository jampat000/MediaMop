import type {
  PrunerJobsInspectionRow,
  PrunerServerInstance,
} from "../../lib/pruner/api";
import type { ProviderTab } from "./pruner-page-types";

export function providerLabel(p: ProviderTab): string {
  if (p === "emby") return "Emby";
  if (p === "jellyfin") return "Jellyfin";
  return "Plex";
}

export function parseServerInstanceId(
  job: PrunerJobsInspectionRow,
): number | null {
  if (!job.payload_json) return null;
  try {
    const parsed = JSON.parse(job.payload_json) as {
      server_instance_id?: unknown;
    };
    const sid = parsed.server_instance_id;
    return typeof sid === "number" && Number.isFinite(sid) ? sid : null;
  } catch {
    return null;
  }
}

export function activeRuleCount(
  scope: PrunerServerInstance["scopes"][number],
): number {
  return [
    scope.missing_primary_media_reported_enabled,
    scope.never_played_stale_reported_enabled,
    scope.watched_tv_reported_enabled,
    scope.watched_movies_reported_enabled,
    scope.watched_movie_low_rating_reported_enabled,
    scope.unwatched_movie_stale_reported_enabled,
  ].filter(Boolean).length;
}

export function defaultScope(scope: "tv" | "movies") {
  return {
    media_scope: scope,
    missing_primary_media_reported_enabled: true,
    never_played_stale_reported_enabled: false,
    never_played_min_age_days: 90,
    watched_tv_reported_enabled: scope === "tv",
    watched_movies_reported_enabled: scope === "movies",
    watched_movie_low_rating_reported_enabled: false,
    watched_movie_low_rating_max_jellyfin_emby_community_rating: 4,
    watched_movie_low_rating_max_plex_audience_rating: 4,
    unwatched_movie_stale_reported_enabled: false,
    unwatched_movie_stale_min_age_days: 90,
    preview_max_items: 500,
    preview_include_genres: [],
    preview_include_people: [],
    preview_include_people_roles: [],
    preview_year_min: null,
    preview_year_max: null,
    preview_include_studios: [],
    preview_include_collections: [],
    scheduled_preview_enabled: false,
    scheduled_preview_interval_seconds: 3600,
    scheduled_preview_hours_limited: false,
    scheduled_preview_days: "",
    scheduled_preview_start: "00:00",
    scheduled_preview_end: "23:59",
    last_scheduled_preview_enqueued_at: null,
    last_preview_run_uuid: null,
    last_preview_at: null,
    last_preview_candidate_count: null,
    last_preview_outcome: null,
    last_preview_error: null,
  };
}

export function providerDisabledInstance(
  provider: ProviderTab,
): PrunerServerInstance {
  return {
    id: 0,
    provider,
    display_name: `${providerLabel(provider)} (not yet connected)`,
    base_url: "",
    enabled: false,
    last_connection_test_at: null,
    last_connection_test_ok: null,
    last_connection_test_detail: null,
    scopes: [defaultScope("tv"), defaultScope("movies")],
  };
}
