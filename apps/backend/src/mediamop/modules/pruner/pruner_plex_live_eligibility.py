"""Eligibility for Plex-only live ``Remove broken library entries`` (no preview snapshot)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import (
    PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import get_scope_settings, get_server_instance
from mediamop.modules.pruner.pruner_schemas import PrunerPlexLiveEligibilityOut


def effective_plex_live_cap(settings: MediaMopSettings, scope_preview_max_items: int) -> int:
    return max(0, min(int(scope_preview_max_items), int(settings.pruner_plex_live_abs_max_items)))


def compute_plex_live_eligibility(
    db: Session,
    settings: MediaMopSettings,
    *,
    instance_id: int,
    media_scope: str,
) -> PrunerPlexLiveEligibilityOut:
    reasons: list[str] = []
    apply_on = bool(settings.pruner_apply_enabled)
    plex_live_on = bool(settings.pruner_plex_live_removal_enabled)

    if not apply_on:
        reasons.append("Pruner live destructive actions are disabled (MEDIAMOP_PRUNER_APPLY_ENABLED=0).")
    if not plex_live_on:
        reasons.append(
            "Plex live removal for this rule family is disabled (MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED=0).",
        )

    inst = get_server_instance(db, instance_id)
    if inst is None:
        reasons.append("Instance not found.")
        return PrunerPlexLiveEligibilityOut(
            eligible=False,
            reasons=reasons,
            apply_feature_enabled=apply_on,
            plex_live_feature_enabled=plex_live_on,
            server_instance_id=instance_id,
            media_scope=media_scope,
            provider="",
            display_name="",
            rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
            rule_enabled=False,
            live_max_items_cap=0,
            required_confirmation_phrase=PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE,
        )

    prov = str(inst.provider)
    if prov != "plex":
        reasons.append("This live-only path is for Plex instances only (use preview → apply for Jellyfin/Emby).")

    sc = get_scope_settings(db, server_instance_id=instance_id, media_scope=media_scope)
    if sc is None:
        reasons.append("Scope row not found for this server instance.")
        rule_enabled = False
        preview_max = 0
    else:
        rule_enabled = bool(sc.missing_primary_media_reported_enabled)
        preview_max = int(sc.preview_max_items)
        if not rule_enabled:
            reasons.append(
                "The missing-primary rule is disabled for this scope — enable it before queuing live removal.",
            )

    cap = effective_plex_live_cap(settings, preview_max) if sc is not None else 0
    if sc is not None and cap < 1:
        reasons.append(
            "Effective live cap is zero (check per-scope item cap and MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS).",
        )

    eligible = len(reasons) == 0
    return PrunerPlexLiveEligibilityOut(
        eligible=eligible,
        reasons=reasons,
        apply_feature_enabled=apply_on,
        plex_live_feature_enabled=plex_live_on,
        server_instance_id=instance_id,
        media_scope=media_scope,
        provider=prov,
        display_name=str(inst.display_name),
        rule_family_id=RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
        rule_enabled=rule_enabled if sc is not None else False,
        live_max_items_cap=int(cap),
        required_confirmation_phrase=PRUNER_PLEX_LIVE_CONFIRMATION_PHRASE,
    )
