"""Refiner HTTP: persisted remux planning defaults (audio/subtitles)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.refiner_remux_rules_settings_service import (
    apply_refiner_remux_rules_settings_put,
    build_refiner_remux_rules_settings_out,
    ensure_refiner_remux_rules_settings_row,
)
from mediamop.modules.refiner.schemas_refiner_remux_rules_settings import (
    RefinerRemuxRulesSettingsOut,
    RefinerRemuxRulesSettingsPutIn,
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


@router.get(
    "/refiner/remux-rules-settings",
    response_model=RefinerRemuxRulesSettingsOut,
)
def get_refiner_remux_rules_settings(
    _user: UserPublicDep,
    db: DbSessionDep,
) -> RefinerRemuxRulesSettingsOut:
    row = ensure_refiner_remux_rules_settings_row(db)
    return build_refiner_remux_rules_settings_out(row)


@router.put(
    "/refiner/remux-rules-settings",
    response_model=RefinerRemuxRulesSettingsOut,
)
def put_refiner_remux_rules_settings(
    body: RefinerRemuxRulesSettingsPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerRemuxRulesSettingsOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )
    try:
        row = apply_refiner_remux_rules_settings_put(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return build_refiner_remux_rules_settings_out(row)
