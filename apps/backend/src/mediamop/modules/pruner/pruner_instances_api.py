"""HTTP: Pruner server instances, scopes, preview runs, and job enqueue."""

from __future__ import annotations

import json
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette import status
from starlette.requests import Request

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.pruner.pruner_apply_eligibility import compute_apply_eligibility
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    clamp_pruner_scheduled_preview_interval_seconds,
)
from mediamop.modules.pruner.pruner_credentials_envelope import (
    PrunerProvider,
    encrypt_envelope,
    envelope_secrets_for_provider,
)
from mediamop.modules.pruner.pruner_instances_service import (
    create_server_instance,
    get_scope_settings,
    get_server_instance,
)
from mediamop.modules.pruner.pruner_job_kinds import (
    PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
    PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
    PRUNER_SERVER_CONNECTION_TEST_JOB_KIND,
)
from mediamop.modules.pruner.pruner_jobs_ops import pruner_enqueue_or_get_job
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.pruner_schemas import (
    PrunerApplyEligibilityOut,
    PrunerApplyHttpIn,
    PrunerConnectionTestIn,
    PrunerEnqueueOut,
    PrunerPreviewEnqueueIn,
    PrunerPreviewRunListItemOut,
    PrunerPreviewRunOut,
    PrunerScopePatchHttpIn,
    PrunerScopeSummaryOut,
    PrunerServerInstanceCreateHttpIn,
    PrunerServerInstanceOut,
    PrunerServerInstancePatchHttpIn,
)
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings
from mediamop.modules.pruner.pruner_server_instance_model import PrunerServerInstance
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["pruner"])


def _scope_row_out(session: Session, row: PrunerScopeSettings) -> PrunerScopeSummaryOut:
    run_uuid: str | None = None
    if row.last_preview_run_id is not None:
        run_uuid = session.scalar(
            select(PrunerPreviewRun.preview_run_id).where(PrunerPreviewRun.id == row.last_preview_run_id),
        )
    return PrunerScopeSummaryOut(
        media_scope=row.media_scope,
        missing_primary_media_reported_enabled=bool(row.missing_primary_media_reported_enabled),
        preview_max_items=int(row.preview_max_items),
        scheduled_preview_enabled=bool(row.scheduled_preview_enabled),
        scheduled_preview_interval_seconds=clamp_pruner_scheduled_preview_interval_seconds(
            int(row.scheduled_preview_interval_seconds),
        ),
        last_scheduled_preview_enqueued_at=row.last_scheduled_preview_enqueued_at,
        last_preview_run_uuid=str(run_uuid) if run_uuid else None,
        last_preview_at=row.last_preview_at,
        last_preview_candidate_count=row.last_preview_candidate_count,
        last_preview_outcome=row.last_preview_outcome,
        last_preview_error=row.last_preview_error,
    )


def _instance_out(session: Session, row: PrunerServerInstance) -> PrunerServerInstanceOut:
    scopes = sorted(row.scope_settings, key=lambda s: s.media_scope)
    return PrunerServerInstanceOut(
        id=int(row.id),
        provider=row.provider,
        display_name=row.display_name,
        base_url=row.base_url,
        enabled=bool(row.enabled),
        last_connection_test_at=row.last_connection_test_at,
        last_connection_test_ok=row.last_connection_test_ok,
        last_connection_test_detail=row.last_connection_test_detail,
        scopes=[_scope_row_out(session, s) for s in scopes],
    )


@router.get("/pruner/instances", response_model=list[PrunerServerInstanceOut])
def list_pruner_instances(
    _user: UserPublicDep,
    db: DbSessionDep,
) -> list[PrunerServerInstanceOut]:
    rows = db.scalars(
        select(PrunerServerInstance)
        .options(selectinload(PrunerServerInstance.scope_settings))
        .order_by(PrunerServerInstance.id.asc()),
    ).all()
    return [_instance_out(db, r) for r in rows]


@router.post("/pruner/instances", response_model=PrunerServerInstanceOut)
def post_pruner_instance(
    body: PrunerServerInstanceCreateHttpIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> PrunerServerInstanceOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")

    prov = cast(PrunerProvider, body.provider)
    row = create_server_instance(
        db,
        settings,
        provider=prov,
        display_name=body.display_name,
        base_url=body.base_url,
        credentials_secrets=body.credentials,
    )
    db.flush()
    row = db.scalars(
        select(PrunerServerInstance)
        .options(selectinload(PrunerServerInstance.scope_settings))
        .where(PrunerServerInstance.id == row.id),
    ).one()
    return _instance_out(db, row)


@router.get("/pruner/instances/{instance_id}", response_model=PrunerServerInstanceOut)
def get_pruner_instance(
    instance_id: Annotated[int, Path(ge=1)],
    _user: UserPublicDep,
    db: DbSessionDep,
) -> PrunerServerInstanceOut:
    row = db.scalars(
        select(PrunerServerInstance)
        .options(selectinload(PrunerServerInstance.scope_settings))
        .where(PrunerServerInstance.id == instance_id),
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found.")
    return _instance_out(db, row)


@router.patch("/pruner/instances/{instance_id}", response_model=PrunerServerInstanceOut)
def patch_pruner_instance(
    instance_id: Annotated[int, Path(ge=1)],
    body: PrunerServerInstancePatchHttpIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> PrunerServerInstanceOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")

    row = db.scalars(
        select(PrunerServerInstance)
        .options(selectinload(PrunerServerInstance.scope_settings))
        .where(PrunerServerInstance.id == instance_id),
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found.")
    if body.display_name is not None:
        row.display_name = body.display_name.strip()
    if body.base_url is not None:
        row.base_url = body.base_url.strip()
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.credentials is not None:
        prov = cast(PrunerProvider, row.provider)
        secrets = envelope_secrets_for_provider(prov, body.credentials)
        row.credentials_ciphertext = encrypt_envelope(settings, provider=prov, secrets=secrets)
    db.flush()
    row = db.scalars(
        select(PrunerServerInstance)
        .options(selectinload(PrunerServerInstance.scope_settings))
        .where(PrunerServerInstance.id == instance_id),
    ).one()
    return _instance_out(db, row)


@router.get(
    "/pruner/instances/{instance_id}/scopes/{media_scope}",
    response_model=PrunerScopeSummaryOut,
    summary="Per-scope Pruner settings (TV episodes vs movie items)",
    description=(
        "TV scope uses **episode-level** candidates for missing primary art in previews. "
        "Movies scope uses **one row per movie library item**."
    ),
)
def get_pruner_scope(
    instance_id: Annotated[int, Path(ge=1)],
    media_scope: Annotated[str, Path(description="`tv` or `movies`")],
    _user: UserPublicDep,
    db: DbSessionDep,
) -> PrunerScopeSummaryOut:
    if media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="media_scope must be tv or movies.")
    sc = get_scope_settings(db, server_instance_id=instance_id, media_scope=media_scope)
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scope not found.")
    return _scope_row_out(db, sc)


@router.patch("/pruner/instances/{instance_id}/scopes/{media_scope}", response_model=PrunerScopeSummaryOut)
def patch_pruner_scope(
    instance_id: Annotated[int, Path(ge=1)],
    media_scope: Annotated[str, Path()],
    body: PrunerScopePatchHttpIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> PrunerScopeSummaryOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    if media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="media_scope must be tv or movies.")
    sc = get_scope_settings(db, server_instance_id=instance_id, media_scope=media_scope)
    if sc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scope not found.")
    if body.missing_primary_media_reported_enabled is not None:
        sc.missing_primary_media_reported_enabled = bool(body.missing_primary_media_reported_enabled)
    if body.preview_max_items is not None:
        sc.preview_max_items = int(body.preview_max_items)
    if body.scheduled_preview_enabled is not None:
        sc.scheduled_preview_enabled = bool(body.scheduled_preview_enabled)
    if body.scheduled_preview_interval_seconds is not None:
        sc.scheduled_preview_interval_seconds = clamp_pruner_scheduled_preview_interval_seconds(
            int(body.scheduled_preview_interval_seconds),
        )
    db.flush()
    return _scope_row_out(db, sc)


@router.get(
    "/pruner/instances/{instance_id}/preview-runs",
    response_model=list[PrunerPreviewRunListItemOut],
    summary="List recent preview runs for this instance (metadata only)",
    description=(
        "Returns newest preview runs first. Optional ``media_scope`` filters to one axis "
        "(``tv`` vs ``movies``). Candidate payloads are omitted; fetch a single run for JSON."
    ),
)
def list_pruner_preview_runs(
    instance_id: Annotated[int, Path(ge=1)],
    _user: UserPublicDep,
    db: DbSessionDep,
    media_scope: Annotated[str | None, Query(description="`tv` or `movies`; omit for all scopes on this instance.")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[PrunerPreviewRunListItemOut]:
    if get_server_instance(db, instance_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found.")
    if media_scope is not None and media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="media_scope query must be tv or movies.",
        )
    stmt = select(PrunerPreviewRun).where(PrunerPreviewRun.server_instance_id == instance_id)
    if media_scope is not None:
        stmt = stmt.where(PrunerPreviewRun.media_scope == media_scope)
    stmt = stmt.order_by(PrunerPreviewRun.created_at.desc(), PrunerPreviewRun.id.desc()).limit(limit)
    rows = db.scalars(stmt).all()
    return [PrunerPreviewRunListItemOut.model_validate(r) for r in rows]


@router.get(
    "/pruner/instances/{instance_id}/preview-runs/{preview_run_uuid}",
    response_model=PrunerPreviewRunOut,
    summary="Fetch one preview run (source of truth for candidates JSON)",
)
def get_pruner_preview_run(
    instance_id: Annotated[int, Path(ge=1)],
    preview_run_uuid: Annotated[str, Path(min_length=36, max_length=36)],
    _user: UserPublicDep,
    db: DbSessionDep,
) -> PrunerPreviewRunOut:
    row = db.scalars(
        select(PrunerPreviewRun).where(
            PrunerPreviewRun.preview_run_id == preview_run_uuid,
            PrunerPreviewRun.server_instance_id == instance_id,
        ),
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview run not found.")
    return PrunerPreviewRunOut.model_validate(row)


@router.get(
    "/pruner/instances/{instance_id}/scopes/{media_scope}/preview-runs/{preview_run_uuid}/apply-eligibility",
    response_model=PrunerApplyEligibilityOut,
    summary="Whether Remove broken library entries can be enqueued for this preview snapshot",
    description=(
        "Read-only gate check for the Jellyfin-only apply slice. This is **not** a preview/dry run — "
        "it only reports whether the snapshot is eligible given instance, scope, outcome, and feature flag."
    ),
)
def get_pruner_apply_eligibility(
    instance_id: Annotated[int, Path(ge=1)],
    media_scope: Annotated[str, Path(description="`tv` or `movies`")],
    preview_run_uuid: Annotated[str, Path(min_length=36, max_length=36)],
    _user: UserPublicDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> PrunerApplyEligibilityOut:
    if media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="media_scope must be tv or movies.")
    if get_server_instance(db, instance_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found.")
    return compute_apply_eligibility(
        db,
        settings,
        instance_id=instance_id,
        media_scope=media_scope,
        preview_run_uuid=preview_run_uuid,
    )


@router.post(
    "/pruner/instances/{instance_id}/scopes/{media_scope}/preview-runs/{preview_run_uuid}/apply",
    response_model=PrunerEnqueueOut,
    summary="Enqueue Remove broken library entries from one preview snapshot (Jellyfin only)",
)
def post_pruner_apply_from_preview(
    instance_id: Annotated[int, Path(ge=1)],
    media_scope: Annotated[str, Path()],
    preview_run_uuid: Annotated[str, Path(min_length=36, max_length=36)],
    body: PrunerApplyHttpIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> PrunerEnqueueOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    if media_scope not in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="media_scope must be tv or movies.")
    if get_server_instance(db, instance_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found.")
    elig = compute_apply_eligibility(
        db,
        settings,
        instance_id=instance_id,
        media_scope=media_scope,
        preview_run_uuid=preview_run_uuid,
    )
    if not elig.eligible:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"reasons": elig.reasons},
        )
    payload = {
        "preview_run_uuid": preview_run_uuid,
        "server_instance_id": instance_id,
        "media_scope": media_scope,
        "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    }
    dedupe = f"pruner:apply:v1:{preview_run_uuid}:{uuid.uuid4()}"
    jid = _enqueue(
        db,
        dedupe_key=dedupe,
        job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
        payload=payload,
    )
    return PrunerEnqueueOut(pruner_job_id=jid)


def _enqueue(
    db: Session,
    *,
    dedupe_key: str,
    job_kind: str,
    payload: dict[str, object],
) -> int:
    job = pruner_enqueue_or_get_job(
        db,
        dedupe_key=dedupe_key,
        job_kind=job_kind,
        payload_json=json.dumps(payload, separators=(",", ":")),
    )
    return int(job.id)


@router.post("/pruner/instances/{instance_id}/connection-test", response_model=PrunerEnqueueOut)
def post_pruner_connection_test(
    instance_id: Annotated[int, Path(ge=1)],
    body: PrunerConnectionTestIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> PrunerEnqueueOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    if get_server_instance(db, instance_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found.")
    dedupe = f"pruner:conn:v1:{instance_id}:{uuid.uuid4()}"
    jid = _enqueue(
        db,
        dedupe_key=dedupe,
        job_kind=PRUNER_SERVER_CONNECTION_TEST_JOB_KIND,
        payload={"server_instance_id": instance_id},
    )
    return PrunerEnqueueOut(pruner_job_id=jid)


@router.post("/pruner/instances/{instance_id}/previews", response_model=PrunerEnqueueOut)
def post_pruner_preview(
    instance_id: Annotated[int, Path(ge=1)],
    body: PrunerPreviewEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> PrunerEnqueueOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    if get_server_instance(db, instance_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found.")
    dedupe = f"pruner:preview:v1:{instance_id}:{body.media_scope}:{uuid.uuid4()}"
    jid = _enqueue(
        db,
        dedupe_key=dedupe,
        job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
        payload={"server_instance_id": instance_id, "media_scope": body.media_scope},
    )
    return PrunerEnqueueOut(pruner_job_id=jid)
