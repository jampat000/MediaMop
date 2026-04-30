"""Refiner HTTP: operator-editable automation settings."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.refiner_operator_settings_service import (
    apply_refiner_operator_settings_put,
    build_refiner_operator_settings_out,
    ensure_refiner_operator_settings_row,
)
from mediamop.modules.refiner.schemas_refiner_operator_settings import (
    RefinerOperatorSettingsOut,
    RefinerOperatorSettingsPutIn,
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


@router.get("/refiner/operator-settings", response_model=RefinerOperatorSettingsOut)
def get_refiner_operator_settings(
    _user: UserPublicDep,
    db: DbSessionDep,
) -> RefinerOperatorSettingsOut:
    row = ensure_refiner_operator_settings_row(db)
    return build_refiner_operator_settings_out(db, row)


@router.put("/refiner/operator-settings", response_model=RefinerOperatorSettingsOut)
def put_refiner_operator_settings(
    body: RefinerOperatorSettingsPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerOperatorSettingsOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")
    try:
        row = apply_refiner_operator_settings_put(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    db.commit()
    return build_refiner_operator_settings_out(db, row)
