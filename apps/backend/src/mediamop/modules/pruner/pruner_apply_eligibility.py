"""Shared rules for Pruner apply-from-preview (Jellyfin Phase 3 slice)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_constants import RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED
from mediamop.modules.pruner.pruner_instances_service import get_server_instance
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.pruner_schemas import PrunerApplyEligibilityOut


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
        )

    prov = str(inst.provider)
    if prov != "jellyfin":
        reasons.append("Remove broken library entries is available for Jellyfin instances only in this release.")

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
        )

    if str(run.media_scope) != media_scope:
        reasons.append("This preview snapshot belongs to a different TV/Movies tab than the current URL.")

    if str(run.rule_family_id) != RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
        reasons.append("This preview snapshot is not eligible for Remove broken library entries.")

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
        rule_family_id=str(run.rule_family_id),
    )
