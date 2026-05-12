"""Persist preview runs (SoT) and mirror latest summary onto ``pruner_scope_settings``."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from sqlalchemy.orm import Session

from mediamop.modules.pruner.pruner_instances_service import get_scope_settings
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings


def apply_latest_preview_denorm(
    session: Session,
    *,
    scope_row: PrunerScopeSettings,
    run: PrunerPreviewRun,
    at: datetime | None = None,
) -> None:
    """Keep ``last_preview_run_id`` aligned with the newest run for (instance, scope)."""

    when = at if at is not None else datetime.now(UTC)
    scope_row.last_preview_run_id = int(run.id)
    scope_row.last_preview_at = when
    scope_row.last_preview_candidate_count = int(run.candidate_count)
    scope_row.last_preview_outcome = str(run.outcome)
    scope_row.last_preview_error = run.error_message


def insert_preview_run(
    session: Session,
    *,
    preview_run_uuid: str,
    server_instance_id: int,
    media_scope: str,
    rule_family_id: str,
    pruner_job_id: int | None,
    candidate_count: int,
    candidates_json: str,
    truncated: bool,
    outcome: str,
    unsupported_detail: str | None,
    error_message: str | None,
) -> PrunerPreviewRun:
    run = PrunerPreviewRun(
        preview_run_id=preview_run_uuid,
        server_instance_id=server_instance_id,
        media_scope=media_scope,
        rule_family_id=rule_family_id,
        pruner_job_id=pruner_job_id,
        candidate_count=candidate_count,
        candidates_json=candidates_json,
        truncated=truncated,
        outcome=outcome,
        unsupported_detail=unsupported_detail,
        error_message=error_message,
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    scope = get_scope_settings(session, server_instance_id=server_instance_id, media_scope=media_scope)
    if scope is not None:
        apply_latest_preview_denorm(
            session,
            scope_row=scope,
            run=run,
            at=run.created_at,
        )
    return run
