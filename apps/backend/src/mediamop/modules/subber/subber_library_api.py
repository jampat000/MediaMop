"""Subber library listing and manual search triggers."""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.subber.subber_job_kinds import (
    SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
    SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
    SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES,
    SUBBER_JOB_KIND_LIBRARY_SYNC_TV,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES,
    SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
)
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_library_service import build_movies_library, build_tv_library
from mediamop.modules.subber.subber_schemas import SubberMoviesLibraryOut, SubberTvLibraryOut
from mediamop.modules.subber.subber_settings_service import ensure_subber_settings_row, language_preferences_list
from mediamop.modules.subber.subber_subtitle_state_service import get_all_for_scope, get_state_by_id
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import current_raw_session_token, verify_csrf_token
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["subber-library"])


class SubberCsrfBody(BaseModel):
    csrf_token: str = Field(..., min_length=1)


@router.get("/library/tv", response_model=SubberTvLibraryOut)
def get_subber_library_tv(
    _user: UserPublicDep,
    db: DbSessionDep,
    status: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    language: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SubberTvLibraryOut:
    row = ensure_subber_settings_row(db)
    prefs = language_preferences_list(row)
    rows = get_all_for_scope(db, "tv")
    return build_tv_library(
        rows,
        prefs=prefs,
        status=status,
        search=search,
        lang_filter=language,
        limit=limit,
        offset=offset,
    )


@router.get("/library/movies", response_model=SubberMoviesLibraryOut)
def get_subber_library_movies(
    _user: UserPublicDep,
    db: DbSessionDep,
    status: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    language: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SubberMoviesLibraryOut:
    row = ensure_subber_settings_row(db)
    prefs = language_preferences_list(row)
    rows = get_all_for_scope(db, "movies")
    return build_movies_library(
        rows,
        prefs=prefs,
        status=status,
        search=search,
        lang_filter=language,
        limit=limit,
        offset=offset,
    )


@router.post("/library/{state_id}/search-now")
def post_subber_search_now(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    request: Request,
    state_id: int,
    body: SubberCsrfBody,
) -> dict[str, str]:
    secret = settings.session_secret or ""
    if not verify_csrf_token(
        secret,
        body.csrf_token,
        raw_session_token=current_raw_session_token(request, settings),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    st = get_state_by_id(db, state_id)
    if st is None:
        raise HTTPException(status_code=404, detail="Unknown state id.")
    kind = SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV if st.media_scope == "tv" else SUBBER_JOB_KIND_SUBTITLE_SEARCH_MOVIES
    dedupe = f"subber:subtitle:manual:{state_id}:{uuid.uuid4()}"
    subber_enqueue_or_get_job(
        db,
        dedupe_key=dedupe,
        job_kind=kind,
        payload_json=json.dumps({"state_id": state_id}, separators=(",", ":")),
    )
    return {"status": "queued"}


@router.post("/library/search-all-missing/tv")
def post_subber_search_all_missing_tv(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    request: Request,
    body: SubberCsrfBody,
) -> dict[str, str]:
    secret = settings.session_secret or ""
    if not verify_csrf_token(
        secret,
        body.csrf_token,
        raw_session_token=current_raw_session_token(request, settings),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    dedupe = f"subber:libscan:manual:tv:{uuid.uuid4()}"
    subber_enqueue_or_get_job(
        db,
        dedupe_key=dedupe,
        job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_TV,
        payload_json=json.dumps({"media_scope": "tv"}, separators=(",", ":")),
    )
    return {"status": "queued"}


@router.post("/library/search-all-missing/movies")
def post_subber_search_all_missing_movies(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    request: Request,
    body: SubberCsrfBody,
) -> dict[str, str]:
    secret = settings.session_secret or ""
    if not verify_csrf_token(
        secret,
        body.csrf_token,
        raw_session_token=current_raw_session_token(request, settings),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    dedupe = f"subber:libscan:manual:movies:{uuid.uuid4()}"
    subber_enqueue_or_get_job(
        db,
        dedupe_key=dedupe,
        job_kind=SUBBER_JOB_KIND_LIBRARY_SCAN_MOVIES,
        payload_json=json.dumps({"media_scope": "movies"}, separators=(",", ":")),
    )
    return {"status": "queued"}


@router.post("/library/sync/tv")
def post_subber_library_sync_tv(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    request: Request,
    body: SubberCsrfBody,
) -> dict[str, str]:
    secret = settings.session_secret or ""
    if not verify_csrf_token(
        secret,
        body.csrf_token,
        raw_session_token=current_raw_session_token(request, settings),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    dedupe = f"subber:libsync:manual:tv:{uuid.uuid4()}"
    subber_enqueue_or_get_job(
        db,
        dedupe_key=dedupe,
        job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_TV,
        payload_json="{}",
    )
    return {"status": "queued"}


@router.post("/library/sync/movies")
def post_subber_library_sync_movies(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    request: Request,
    body: SubberCsrfBody,
) -> dict[str, str]:
    secret = settings.session_secret or ""
    if not verify_csrf_token(
        secret,
        body.csrf_token,
        raw_session_token=current_raw_session_token(request, settings),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    dedupe = f"subber:libsync:manual:movies:{uuid.uuid4()}"
    subber_enqueue_or_get_job(
        db,
        dedupe_key=dedupe,
        job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES,
        payload_json="{}",
    )
    return {"status": "queued"}
