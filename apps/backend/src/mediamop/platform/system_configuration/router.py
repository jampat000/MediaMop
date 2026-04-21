"""Suite configuration export/import under ``/api/v1/system``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.configuration_bundle.service import apply_configuration_bundle, build_configuration_bundle
from mediamop.platform.suite_settings.schemas import ConfigurationBundleImportIn

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/suite-configuration-bundle")
def get_suite_configuration_bundle(_user: RequireOperatorDep, db: DbSessionDep) -> dict:
    try:
        return build_configuration_bundle(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.put("/suite-configuration-bundle")
def put_suite_configuration_bundle(
    body: ConfigurationBundleImportIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> dict:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your confirmation token expired. Refresh the page and try again.",
        )
    try:
        apply_configuration_bundle(db, body.bundle)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return build_configuration_bundle(db)
