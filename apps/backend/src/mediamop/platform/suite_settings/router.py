"""Suite-wide settings (Global) and read-only security overview — not Fetcher/Sonarr/Radarr."""

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
from mediamop.platform.auth.deps_auth import UserPublicDep
from mediamop.platform.configuration_bundle.service import apply_configuration_bundle, build_configuration_bundle
from mediamop.platform.suite_settings.schemas import (
    ConfigurationBundleImportIn,
    SuiteSecurityOverviewOut,
    SuiteSettingsOut,
    SuiteSettingsPutIn,
)
from mediamop.platform.suite_settings.security_overview import build_suite_security_overview
from mediamop.platform.suite_settings.service import apply_suite_settings_put, build_suite_settings_out, ensure_suite_settings_row

router = APIRouter(tags=["suite"])


@router.get("/suite/settings", response_model=SuiteSettingsOut)
def get_suite_settings(_user: UserPublicDep, db: DbSessionDep) -> SuiteSettingsOut:
    """Names and notices stored in the app database (any signed-in user may read)."""

    row = ensure_suite_settings_row(db)
    return build_suite_settings_out(row)


@router.put("/suite/settings", response_model=SuiteSettingsOut)
def put_suite_settings(
    body: SuiteSettingsPutIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> SuiteSettingsOut:
    """Update suite display text — operators and admins only."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your confirmation token expired. Refresh the page and try again.",
        )
    try:
        out = apply_suite_settings_put(
            db,
            product_display_name=body.product_display_name,
            signed_in_home_notice=body.signed_in_home_notice,
            app_timezone=body.app_timezone,
            log_retention_days=body.log_retention_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return out


@router.get("/suite/settings/configuration-bundle")
@router.get("/suite/configuration-bundle")
def get_configuration_bundle(_user: RequireOperatorDep, db: DbSessionDep) -> dict:
    """Export suite + module configuration as JSON (operators/admins only — contains secrets)."""

    try:
        return build_configuration_bundle(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.put("/suite/settings/configuration-bundle")
@router.put("/suite/configuration-bundle")
def put_configuration_bundle(
    body: ConfigurationBundleImportIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> dict:
    """Replace suite + module configuration from a prior export (operators/admins only)."""

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


@router.get("/suite/security-overview", response_model=SuiteSecurityOverviewOut)
def get_suite_security_overview(
    _user: UserPublicDep,
    settings: SettingsDep,
) -> SuiteSecurityOverviewOut:
    """Read-only snapshot of sign-in protection (from startup configuration, not the database)."""

    return build_suite_security_overview(settings)
