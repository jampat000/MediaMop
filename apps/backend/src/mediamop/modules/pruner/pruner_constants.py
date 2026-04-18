"""Pruner domain constants (scopes, rule families, preview semantics)."""

from __future__ import annotations

MEDIA_SCOPE_TV = "tv"
MEDIA_SCOPE_MOVIES = "movies"

RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED = "missing_primary_media_reported"
RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED = "never_played_stale_reported"
RULE_FAMILY_WATCHED_TV_REPORTED = "watched_tv_reported"
RULE_FAMILY_WATCHED_MOVIES_REPORTED = "watched_movies_reported"
RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED = "watched_movie_low_rating_reported"
RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED = "unwatched_movie_stale_reported"
RULE_FAMILY_GENRE_MATCH_REPORTED = "genre_match_reported"
RULE_FAMILY_STUDIO_MATCH_REPORTED = "studio_match_reported"
RULE_FAMILY_PEOPLE_MATCH_REPORTED = "people_match_reported"
RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED = "year_range_match_reported"

PRUNER_APPLY_LABEL_MISSING_PRIMARY = "Remove broken library entries"
PRUNER_APPLY_LABEL_NEVER_PLAYED_STALE = "Remove stale never-played library entries"
PRUNER_APPLY_LABEL_WATCHED_TV = "Remove watched TV entries"
PRUNER_APPLY_LABEL_WATCHED_MOVIES = "Remove watched movie entries"
PRUNER_APPLY_LABEL_WATCHED_MOVIE_LOW_RATING = "Remove watched low-rated movie entries"
PRUNER_APPLY_LABEL_UNWATCHED_MOVIE_STALE = "Remove stale unwatched movie entries"
PRUNER_APPLY_LABEL_GENRE_MATCH = "Remove items matching selected genres"
PRUNER_APPLY_LABEL_STUDIO_MATCH = "Remove items from selected studios"
PRUNER_APPLY_LABEL_PEOPLE_MATCH = "Remove items involving selected people"
PRUNER_APPLY_LABEL_YEAR_RANGE_MATCH = "Remove items from selected year range"

PRUNER_DEFAULT_NEVER_PLAYED_MIN_AGE_DAYS = 90
PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MIN = 7
PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MAX = 3650

# Jellyfin/Emby ``CommunityRating`` on library Items (0–10 inclusive on that field for this product slice).
PRUNER_WATCHED_MOVIE_LOW_RATING_COMMUNITY_MIN = 0.0
PRUNER_WATCHED_MOVIE_LOW_RATING_COMMUNITY_MAX = 10.0
PRUNER_DEFAULT_WATCHED_MOVIE_LOW_RATING_MAX_JF_EMBY_COMMUNITY = 4.0
PRUNER_DEFAULT_WATCHED_MOVIE_LOW_RATING_MAX_PLEX_AUDIENCE = 4.0

# Legacy confirmation phrase for the retired Plex live-removal POST body (still returned read-only by eligibility).
PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE = "PLEX BROKEN LIBRARY LIVE CONFIRM"

# Scheduled preview interval (seconds) — per ``pruner_scope_settings`` row, clamped on write.
PRUNER_SCHEDULED_PREVIEW_INTERVAL_MIN_SECONDS = 60
PRUNER_SCHEDULED_PREVIEW_INTERVAL_MAX_SECONDS = 86_400

# Preview-only production/release year bounds (inclusive) — Jellyfin/Emby ``ProductionYear``, Plex leaf ``year``.
PRUNER_PREVIEW_YEAR_FILTER_MIN = 1900
PRUNER_PREVIEW_YEAR_FILTER_MAX = 2100


def clamp_preview_year_bound(raw: int | None) -> int | None:
    """Clamp a single year bound to the preview filter range; ``None`` stays unset."""

    if raw is None:
        return None
    return max(
        PRUNER_PREVIEW_YEAR_FILTER_MIN,
        min(PRUNER_PREVIEW_YEAR_FILTER_MAX, int(raw)),
    )


def clamp_never_played_min_age_days(raw: int) -> int:
    """Clamp per-scope ``never_played_min_age_days`` (library DateCreated age gate)."""

    return max(
        PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MIN,
        min(PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MAX, int(raw)),
    )


def _clamp_watched_movie_low_rating_numeric_ceiling_0_10(raw: float) -> float:
    return max(
        PRUNER_WATCHED_MOVIE_LOW_RATING_COMMUNITY_MIN,
        min(PRUNER_WATCHED_MOVIE_LOW_RATING_COMMUNITY_MAX, float(raw)),
    )


def clamp_watched_movie_low_rating_max_jellyfin_emby_community_rating(raw: float) -> float:
    """Clamp per-scope ceiling for Jellyfin/Emby Items ``CommunityRating`` (0–10 on that field)."""

    return _clamp_watched_movie_low_rating_numeric_ceiling_0_10(raw)


def clamp_watched_movie_low_rating_max_plex_audience_rating(raw: float) -> float:
    """Clamp per-scope ceiling for Plex movie leaf ``audienceRating`` (0–10 numeric in this slice)."""

    return _clamp_watched_movie_low_rating_numeric_ceiling_0_10(raw)


def pruner_apply_operator_label(rule_family_id: str) -> str:
    """Operator-facing apply button / activity action label for a preview snapshot rule."""

    if rule_family_id == RULE_FAMILY_WATCHED_TV_REPORTED:
        return PRUNER_APPLY_LABEL_WATCHED_TV
    if rule_family_id == RULE_FAMILY_WATCHED_MOVIES_REPORTED:
        return PRUNER_APPLY_LABEL_WATCHED_MOVIES
    if rule_family_id == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED:
        return PRUNER_APPLY_LABEL_WATCHED_MOVIE_LOW_RATING
    if rule_family_id == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED:
        return PRUNER_APPLY_LABEL_UNWATCHED_MOVIE_STALE
    if rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
        return PRUNER_APPLY_LABEL_NEVER_PLAYED_STALE
    if rule_family_id == RULE_FAMILY_GENRE_MATCH_REPORTED:
        return PRUNER_APPLY_LABEL_GENRE_MATCH
    if rule_family_id == RULE_FAMILY_STUDIO_MATCH_REPORTED:
        return PRUNER_APPLY_LABEL_STUDIO_MATCH
    if rule_family_id == RULE_FAMILY_PEOPLE_MATCH_REPORTED:
        return PRUNER_APPLY_LABEL_PEOPLE_MATCH
    if rule_family_id == RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED:
        return PRUNER_APPLY_LABEL_YEAR_RANGE_MATCH
    return PRUNER_APPLY_LABEL_MISSING_PRIMARY


def pruner_preview_rule_families_jf_emby() -> frozenset[str]:
    """Rule families that use Jellyfin/Emby Items API preview in this product slice."""

    return frozenset(
        {
            RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
            RULE_FAMILY_WATCHED_TV_REPORTED,
            RULE_FAMILY_WATCHED_MOVIES_REPORTED,
            RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
            RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
            RULE_FAMILY_GENRE_MATCH_REPORTED,
            RULE_FAMILY_STUDIO_MATCH_REPORTED,
            RULE_FAMILY_PEOPLE_MATCH_REPORTED,
            RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
        },
    )


def clamp_pruner_scheduled_preview_interval_seconds(raw: int) -> int:
    """Operator-facing cadence floor/ceiling for ``scheduled_preview_interval_seconds``."""

    return max(
        PRUNER_SCHEDULED_PREVIEW_INTERVAL_MIN_SECONDS,
        min(PRUNER_SCHEDULED_PREVIEW_INTERVAL_MAX_SECONDS, int(raw)),
    )

# TV preview: one row per **episode** missing a primary image (honest granularity for UI + removal).
# Movies preview: one row per **movie library item** missing a primary image.
