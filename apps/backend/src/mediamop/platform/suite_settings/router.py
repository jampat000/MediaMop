"""Suite-wide settings (Global) and read-only security overview — not module *arr* pages."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
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
    SuiteConfigurationBackupItemOut,
    SuiteConfigurationBackupListOut,
    SuiteLogCountsOut,
    SuiteLogEntryOut,
    SuiteLogsOut,
    SuiteMetricsOut,
    SuiteMetricsRouteOut,
    SuiteSecurityOverviewOut,
    SuiteSettingsOut,
    SuiteSettingsPutIn,
    SuiteUpdateStartIn,
    SuiteUpdateStartOut,
    SuiteUpdateStatusOut,
)
from mediamop.platform.metrics.service import build_runtime_metrics_summary
from mediamop.platform.suite_settings.security_overview import build_suite_security_overview
from mediamop.platform.suite_settings.logs_service import prune_log_file, read_suite_logs
from mediamop.platform.suite_settings.service import apply_suite_settings_put, build_suite_settings_out, ensure_suite_settings_row
from mediamop.platform.suite_settings.suite_configuration_backup_service import (
    get_suite_configuration_backup_file_path,
    list_suite_configuration_backups,
)
from mediamop.platform.suite_settings.update_service import build_suite_update_status, start_suite_update_now

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
            setup_wizard_state=body.setup_wizard_state,
            app_timezone=body.app_timezone,
            log_retention_days=body.log_retention_days,
            configuration_backup_enabled=body.configuration_backup_enabled,
            configuration_backup_interval_hours=body.configuration_backup_interval_hours,
            configuration_backup_preferred_time=body.configuration_backup_preferred_time,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    prune_log_file(settings, keep_days=out.log_retention_days)
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


@router.get("/suite/configuration-backups", response_model=SuiteConfigurationBackupListOut)
def get_configuration_backups(_user: RequireOperatorDep, db: DbSessionDep, settings: SettingsDep) -> SuiteConfigurationBackupListOut:
    directory, rows = list_suite_configuration_backups(db, settings=settings)
    return SuiteConfigurationBackupListOut(
        directory=directory,
        items=[
            SuiteConfigurationBackupItemOut(
                id=r.id,
                created_at=r.created_at,
                file_name=r.file_name,
                size_bytes=r.size_bytes,
            )
            for r in rows
        ],
    )


@router.get("/suite/configuration-backups/{backup_id}/download")
def download_configuration_backup(
    backup_id: int,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> FileResponse:
    try:
        path, row = get_suite_configuration_backup_file_path(db, settings=settings, backup_id=backup_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/json", filename=row.file_name)


@router.get("/suite/security-overview", response_model=SuiteSecurityOverviewOut)
def get_suite_security_overview(
    _user: UserPublicDep,
    settings: SettingsDep,
) -> SuiteSecurityOverviewOut:
    """Read-only snapshot of sign-in protection (from startup configuration, not the database)."""

    return build_suite_security_overview(settings)


@router.get("/suite/update-status", response_model=SuiteUpdateStatusOut)
@router.get("/suite/settings/update-status", response_model=SuiteUpdateStatusOut)
def get_suite_update_status(_user: UserPublicDep) -> SuiteUpdateStatusOut:
    """Read-only update check for the signed-in Settings page."""

    return build_suite_update_status()


@router.get("/suite/update-now")
@router.get("/suite/settings/update-now")
def get_suite_update_now_redirect() -> RedirectResponse:
    """If a browser lands on the upgrade API after restart, send it back to the app."""

    return RedirectResponse(url="/app/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/suite/update-now", response_model=SuiteUpdateStartOut)
@router.post("/suite/settings/update-now", response_model=SuiteUpdateStartOut)
def post_suite_update_now(
    body: SuiteUpdateStartIn,
    request: Request,
    _user: RequireOperatorDep,
    settings: SettingsDep,
) -> SuiteUpdateStartOut:
    """Start an in-place Windows upgrade from the latest published installer."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your confirmation token expired. Refresh the page and try again.",
        )
    try:
        return start_suite_update_now(settings)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not start the upgrade: {exc}",
        ) from exc


@router.get("/suite/logs", response_model=SuiteLogsOut)
def get_suite_logs(
    _user: UserPublicDep,
    settings: SettingsDep,
    level: str | None = None,
    search: str | None = None,
    has_exception: bool | None = None,
    limit: int = 100,
) -> SuiteLogsOut:
    items, total, counts = read_suite_logs(
        settings,
        level=level,
        search=search,
        has_exception=has_exception,
        limit=limit,
    )
    return SuiteLogsOut(
        items=[
            SuiteLogEntryOut(
                timestamp=item.timestamp,
                level=item.level,
                component=item.component,
                message=item.message,
                detail=item.detail,
                traceback=item.traceback,
                source=item.source,
                logger=item.logger,
                correlation_id=item.correlation_id,
                job_id=item.job_id,
            )
            for item in items
        ],
        total=total,
        counts=SuiteLogCountsOut(
            error=counts["ERROR"],
            warning=counts["WARNING"],
            information=counts["INFO"],
        ),
    )


@router.get("/suite/metrics", response_model=SuiteMetricsOut)
def get_suite_metrics(_user: UserPublicDep) -> SuiteMetricsOut:
    summary = build_runtime_metrics_summary()
    return SuiteMetricsOut(
        uptime_seconds=float(summary["uptime_seconds"]),
        total_requests=int(summary["total_requests"]),
        average_response_ms=float(summary["average_response_ms"]),
        error_log_count=int(summary["error_log_count"]),
        status_counts={k: int(v) for k, v in dict(summary["status_counts"]).items()},
        busiest_routes=[
            SuiteMetricsRouteOut(
                route=str(row["route"]),
                request_count=int(row["request_count"]),
                average_response_ms=float(row["average_response_ms"]),
            )
            for row in list(summary["busiest_routes"])
        ],
    )
