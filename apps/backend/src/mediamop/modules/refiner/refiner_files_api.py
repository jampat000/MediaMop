"""Refiner HTTP: the Files screen — ``/api/v1/refiner/files``.

The screen this serves is the one that answers "why isn't this file processing?", which
Refiner previously could not answer at all: the scan decided and moved on, and the reason
never left the function that produced it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Path, Query, Request
from starlette import status as http_status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.modules.refiner.refiner_file_state_service import forget_file, list_files, status_counts
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.schemas_refiner_files import (
    RefinerFileForgetIn,
    RefinerFileOut,
    RefinerFilesPageOut,
    RefinerFileStatusName,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["refiner"])


def _verify_csrf(request: Request, settings: MediaMopSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")


@router.get("/refiner/files", response_model=RefinerFilesPageOut)
def get_refiner_files(
    _user: UserPublicDep,
    db: DbSessionDep,
    library_id: int | None = Query(default=None, ge=1),
    file_status: RefinerFileStatusName | None = Query(default=None),
    path_contains: str | None = Query(default=None, max_length=400),
    within_days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=200, ge=1, le=1000),
) -> RefinerFilesPageOut:
    """Files Refiner has seen, with the reason it is or is not working on each."""

    since = datetime.now(UTC) - timedelta(days=within_days) if within_days else None
    rows = list_files(
        db,
        library_id=library_id,
        status=file_status,
        path_contains=path_contains,
        since=since,
        limit=limit,
    )
    names = {row.id: row.name for row in db.query(RefinerLibraryRow).all()}
    files = [
        RefinerFileOut(
            id=row.id,
            library_id=row.library_id,
            library_name=names.get(row.library_id, "Unknown library"),
            relative_path=row.relative_path,
            status=row.status,  # type: ignore[arg-type]
            status_reason=row.status_reason,
            blocked_by_connection=row.blocked_by_connection,
            size_bytes=row.size_bytes,
            last_seen_at=row.last_seen_at,
            last_attempt_at=row.last_attempt_at,
        )
        for row in rows
    ]
    return RefinerFilesPageOut(
        files=files,
        status_counts=status_counts(db, library_id=library_id),
        returned=len(files),
        limit=limit,
    )


@router.delete("/refiner/files/{file_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_refiner_file(
    body: RefinerFileForgetIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    file_id: int = Path(ge=1),
) -> None:
    """Forget a file. Removes MediaMop's record of it, never the file on disk."""

    _verify_csrf(request, settings, body.csrf_token)
    row = db.get(RefinerFileRow, file_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="MediaMop has no record of that file.")
    forget_file(db, row)
    db.commit()
