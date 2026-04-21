"""Suite configuration export/import under ``/api/v1/system``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.configuration_bundle.service import apply_configuration_bundle, build_configuration_bundle
from mediamop.platform.suite_settings.schemas import (
    ConfigurationBundleImportIn,
    SuiteConfigurationBackupItemOut,
    SuiteConfigurationBackupListOut,
)
from mediamop.platform.suite_settings.suite_configuration_backup_service import (
    get_suite_configuration_backup_file_path,
    list_suite_configuration_backups,
)

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


@router.get("/suite-configuration-backups", response_model=SuiteConfigurationBackupListOut)
def get_suite_configuration_backups(_user: RequireOperatorDep, db: DbSessionDep, settings: SettingsDep) -> SuiteConfigurationBackupListOut:
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


@router.get("/suite-configuration-backups/{backup_id}/download")
def download_suite_configuration_backup(
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
