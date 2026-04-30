"""Refiner HTTP: persisted watched / work / output folders (Refiner-owned)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_path_settings_schemas import RefinerPathSettingsOut, RefinerPathSettingsPutIn
from mediamop.modules.refiner.refiner_path_settings_service import (
    apply_refiner_path_settings_put,
    build_refiner_path_settings_get_out,
    ensure_refiner_path_settings_row,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.deps_auth import UserPublicDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)

router = APIRouter(tags=["refiner"])


def _out_from_session(db, settings: MediaMopSettings) -> RefinerPathSettingsOut:
    row = ensure_refiner_path_settings_row(db)
    payload = build_refiner_path_settings_get_out(row=row, settings=settings)
    return RefinerPathSettingsOut.model_validate(payload)


@router.get(
    "/refiner/path-settings",
    response_model=RefinerPathSettingsOut,
)
def get_refiner_path_settings(
    _user: UserPublicDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerPathSettingsOut:
    """Read saved Refiner path roles plus the resolved default work/temp path (shown before first save)."""

    return _out_from_session(db, settings)


@router.put(
    "/refiner/path-settings",
    response_model=RefinerPathSettingsOut,
)
def put_refiner_path_settings(
    body: RefinerPathSettingsPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerPathSettingsOut:
    """Persist Refiner path settings with hard validation (overlap, existence, required output)."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    try:
        apply_refiner_path_settings_put(
            db,
            settings,
            watched_folder=body.refiner_watched_folder,
            work_folder=body.refiner_work_folder,
            output_folder=body.refiner_output_folder,
            tv_paths_included=body.refiner_tv_paths_included,
            tv_watched_folder=body.refiner_tv_watched_folder,
            tv_work_folder=body.refiner_tv_work_folder,
            tv_output_folder=body.refiner_tv_output_folder,
            movie_watched_folder_check_interval_seconds=body.movie_watched_folder_check_interval_seconds,
            tv_watched_folder_check_interval_seconds=body.tv_watched_folder_check_interval_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _out_from_session(db, settings)
