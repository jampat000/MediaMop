"""Pruner domain constants (scopes, rule families, preview semantics)."""

from __future__ import annotations

MEDIA_SCOPE_TV = "tv"
MEDIA_SCOPE_MOVIES = "movies"

RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED = "missing_primary_media_reported"
RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED = "never_played_stale_reported"

PRUNER_APPLY_LABEL_MISSING_PRIMARY = "Remove broken library entries"
PRUNER_APPLY_LABEL_NEVER_PLAYED_STALE = "Remove stale never-played library entries"

PRUNER_DEFAULT_NEVER_PLAYED_MIN_AGE_DAYS = 90
PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MIN = 7
PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MAX = 3650

# Plex-only live removal: operator must POST this exact phrase (case-sensitive, no surrounding spaces).
PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE = "PLEX BROKEN LIBRARY LIVE CONFIRM"

# Scheduled preview interval (seconds) — per ``pruner_scope_settings`` row, clamped on write.
PRUNER_SCHEDULED_PREVIEW_INTERVAL_MIN_SECONDS = 60
PRUNER_SCHEDULED_PREVIEW_INTERVAL_MAX_SECONDS = 86_400


def clamp_never_played_min_age_days(raw: int) -> int:
    """Clamp per-scope ``never_played_min_age_days`` (library DateCreated age gate)."""

    return max(
        PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MIN,
        min(PRUNER_NEVER_PLAYED_MIN_AGE_DAYS_MAX, int(raw)),
    )


def pruner_apply_operator_label(rule_family_id: str) -> str:
    """Operator-facing apply button / activity action label for a preview snapshot rule."""

    if rule_family_id == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
        return PRUNER_APPLY_LABEL_NEVER_PLAYED_STALE
    return PRUNER_APPLY_LABEL_MISSING_PRIMARY


def pruner_preview_rule_families_jf_emby() -> frozenset[str]:
    """Rule families that use Jellyfin/Emby Items API preview in this product slice."""

    return frozenset({RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED, RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED})


def clamp_pruner_scheduled_preview_interval_seconds(raw: int) -> int:
    """Operator-facing cadence floor/ceiling for ``scheduled_preview_interval_seconds``."""

    return max(
        PRUNER_SCHEDULED_PREVIEW_INTERVAL_MIN_SECONDS,
        min(PRUNER_SCHEDULED_PREVIEW_INTERVAL_MAX_SECONDS, int(raw)),
    )

# TV preview: one row per **episode** missing a primary image (honest granularity for UI + removal).
# Movies preview: one row per **movie library item** missing a primary image.
