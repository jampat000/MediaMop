"""Fetcher Arr search (missing / upgrade) HTTP — manual enqueue only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.fetcher.fetcher_arr_search_enqueue import enqueue_manual_arr_search_job
from mediamop.modules.fetcher.schemas_arr_search_manual import (
    FetcherArrSearchManualEnqueueIn,
    FetcherArrSearchManualEnqueueOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)

router = APIRouter(tags=["fetcher"])


@router.post(
    "/fetcher/arr-search/enqueue",
    response_model=FetcherArrSearchManualEnqueueOut,
)
def post_fetcher_arr_search_enqueue(
    body: FetcherArrSearchManualEnqueueIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> FetcherArrSearchManualEnqueueOut:
    """Fetcher: enqueue one manual Sonarr/Radarr missing or upgrade search job (``fetcher_jobs`` only)."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    job = enqueue_manual_arr_search_job(db, scope=body.scope)
    return FetcherArrSearchManualEnqueueOut(
        job_id=job.id,
        dedupe_key=job.dedupe_key,
        job_kind=job.job_kind,
    )
