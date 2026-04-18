"""Shared rules for Pruner apply-from-preview (Jellyfin, Emby, and Plex snapshot-bound)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_GENRE_MATCH_REPORTED,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
    RULE_FAMILY_PEOPLE_MATCH_REPORTED,
    RULE_FAMILY_STUDIO_MATCH_REPORTED,
    RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
    RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
    RULE_FAMILY_WATCHED_TV_REPORTED,
    RULE_FAMILY_YEAR_RANGE_MATCH_REPORTED,
    pruner_apply_operator_label,
)
from mediamop.modules.pruner.pruner_instances_service import get_scope_settings, get_server_instance
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.pruner_schemas import PrunerApplyEligibilityOut

_APPLY_SUPPORTED_RULES = frozenset(
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


def compute_apply_eligibility(
    db: Session,
    settings: MediaMopSettings,
    *,
    instance_id: int,
    media_scope: str,
    preview_run_uuid: str,
) -> PrunerApplyEligibilityOut:
    reasons: list[str] = []
    feature_on = bool(settings.pruner_apply_enabled)
    if not feature_on:
        reasons.append("Live apply is disabled for this MediaMop process (MEDIAMOP_PRUNER_APPLY_ENABLED=0).")

    inst = get_server_instance(db, instance_id)
    if inst is None:
        reasons.append("Instance not found.")
        return PrunerApplyEligibilityOut(
            eligible=False,
            reasons=reasons,
            apply_feature_enabled=feature_on,
            preview_run_id=preview_run_uuid,
            server_instance_id=instance_id,
            media_scope=media_scope,
            provider="",
            display_name="",
            preview_created_at=None,
            candidate_count=0,
            preview_outcome="",
            rule_family_id="",
            apply_operator_label="",
        )

    prov = str(inst.provider)
    if prov not in ("jellyfin", "emby", "plex"):
        reasons.append(
            "Applying from preview snapshots is available for Jellyfin, Emby, and Plex instances only in this release.",
        )

    run = db.scalars(
        select(PrunerPreviewRun).where(
            PrunerPreviewRun.preview_run_id == preview_run_uuid,
            PrunerPreviewRun.server_instance_id == instance_id,
        ),
    ).first()
    if run is None:
        reasons.append("Preview snapshot not found for this instance.")
        return PrunerApplyEligibilityOut(
            eligible=False,
            reasons=reasons,
            apply_feature_enabled=feature_on,
            preview_run_id=preview_run_uuid,
            server_instance_id=instance_id,
            media_scope=media_scope,
            provider=prov,
            display_name=inst.display_name,
            preview_created_at=None,
            candidate_count=0,
            preview_outcome="",
            rule_family_id="",
            apply_operator_label="",
        )

    rid = str(run.rule_family_id)
    apply_label = pruner_apply_operator_label(rid)

    if str(run.media_scope) != media_scope:
        reasons.append("This preview snapshot belongs to a different TV/Movies tab than the current URL.")

    if rid == RULE_FAMILY_WATCHED_TV_REPORTED and str(run.media_scope) != MEDIA_SCOPE_TV:
        reasons.append("Watched TV apply is only defined for TV (episodes) preview snapshots.")

    if rid == RULE_FAMILY_WATCHED_MOVIES_REPORTED and str(run.media_scope) != MEDIA_SCOPE_MOVIES:
        reasons.append("Watched movies apply is only defined for Movies preview snapshots.")

    if rid == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED and str(run.media_scope) != MEDIA_SCOPE_MOVIES:
        reasons.append("Watched low-rating movies apply is only defined for Movies preview snapshots.")

    if rid == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED and str(run.media_scope) != MEDIA_SCOPE_MOVIES:
        reasons.append("Unwatched stale movies apply is only defined for Movies preview snapshots.")

    if rid not in _APPLY_SUPPORTED_RULES:
        reasons.append("This preview snapshot's rule family is not supported for apply in this release.")
    else:
        sc = get_scope_settings(db, server_instance_id=instance_id, media_scope=media_scope)
        if sc is None:
            reasons.append("Scope settings row missing.")
        elif rid == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED and not bool(sc.missing_primary_media_reported_enabled):
            reasons.append(
                f"{apply_label} is not enabled for this scope (missing-primary rule toggle).",
            )
        elif rid == RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED and not bool(sc.never_played_stale_reported_enabled):
            reasons.append(
                f"{apply_label} is not enabled for this scope (never-played stale rule toggle).",
            )
        elif rid == RULE_FAMILY_WATCHED_TV_REPORTED and not bool(sc.watched_tv_reported_enabled):
            reasons.append(
                f"{apply_label} is not enabled for this scope (watched TV rule toggle).",
            )
        elif rid == RULE_FAMILY_WATCHED_MOVIES_REPORTED and not bool(sc.watched_movies_reported_enabled):
            reasons.append(
                f"{apply_label} is not enabled for this scope (watched movies rule toggle).",
            )
        elif rid == RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED and not bool(sc.watched_movie_low_rating_reported_enabled):
            reasons.append(
                f"{apply_label} is not enabled for this scope (watched low-rating movies rule toggle).",
            )
        elif rid == RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED and not bool(sc.unwatched_movie_stale_reported_enabled):
            reasons.append(
                f"{apply_label} is not enabled for this scope (unwatched stale movies rule toggle).",
            )

    if str(run.outcome) != "success":
        reasons.append("Preview outcome must be success before applying this snapshot.")

    if int(run.candidate_count) < 1:
        reasons.append("This preview snapshot has no candidates to apply.")

    eligible = len(reasons) == 0
    return PrunerApplyEligibilityOut(
        eligible=eligible,
        reasons=reasons,
        apply_feature_enabled=feature_on,
        preview_run_id=str(run.preview_run_id),
        server_instance_id=int(run.server_instance_id),
        media_scope=str(run.media_scope),
        provider=prov,
        display_name=inst.display_name,
        preview_created_at=run.created_at,
        candidate_count=int(run.candidate_count),
        preview_outcome=str(run.outcome),
        rule_family_id=rid,
        apply_operator_label=apply_label if rid in _APPLY_SUPPORTED_RULES else "",
    )
