"""Refiner HTTP: libraries and rule sets — ``/api/v1/refiner/libraries``.

Adding a Refiner library is a POST, not a migration. That is the whole point of
ADR-0014, and #346 makes reaching the v1 API and the generated schema the standing gate
for the epic.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Request
from sqlalchemy import select
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_library_crud import (
    RefinerLibraryError,
    active_job_count_for_library,
    create_library,
    create_rule_set,
    delete_library,
    delete_rule_set,
    reorder_libraries,
    rule_set_usage_count,
    update_library,
    update_rule_set,
)
from mediamop.modules.refiner.refiner_library_discovery import (
    RefinerDiscoveryError,
    discoverable_libraries,
    import_libraries,
    resync_drift,
    unlink_library,
)
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow, RefinerRuleSetRow
from mediamop.modules.refiner.refiner_library_service import list_libraries, manager_connection_ids_for
from mediamop.modules.refiner.schemas_refiner_libraries import (
    DiscoverableLibraryOut,
    LibraryDriftOut,
    RefinerLibraryCreateIn,
    RefinerLibraryDeleteIn,
    RefinerLibraryImportIn,
    RefinerLibraryOut,
    RefinerLibraryReorderIn,
    RefinerLibraryUpdateIn,
    RefinerRuleSetIn,
    RefinerRuleSetOut,
)
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.auth.deps_auth import UserPublicDep
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow

router = APIRouter(tags=["refiner"])


def _verify_csrf(request: Request, settings: MediaMopSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")


def _library_out(db, row: RefinerLibraryRow) -> RefinerLibraryOut:
    return RefinerLibraryOut(
        id=row.id,
        name=row.name,
        enabled=row.enabled,
        media_scope=row.media_scope,  # type: ignore[arg-type]
        display_order=row.display_order,
        watched_folder=row.watched_folder,
        work_folder=row.work_folder,
        output_folder=row.output_folder,
        media_extensions_csv=row.media_extensions_csv,
        exclude_markers_csv=row.exclude_markers_csv,
        include_patterns_csv=row.include_patterns_csv,
        exclude_patterns_csv=row.exclude_patterns_csv,
        min_file_size_mb=row.min_file_size_mb,
        max_file_size_mb=row.max_file_size_mb,
        min_file_age_seconds=row.min_file_age_seconds,
        exclude_hidden=row.exclude_hidden,
        top_level_only=row.top_level_only,
        scan_interval_seconds=row.scan_interval_seconds,
        hold_minutes=row.hold_minutes,
        file_detection_interval_seconds=row.file_detection_interval_seconds,
        ignore_size_changes=row.ignore_size_changes,
        skip_access_tests=row.skip_access_tests,
        file_system_events_enabled=row.file_system_events_enabled,
        schedule_grid=row.schedule_grid or "",
        max_attempts=int(row.max_attempts),
        retry_backoff_seconds=int(row.retry_backoff_seconds),
        retry_execution_failures=bool(row.retry_execution_failures),
        retry_preflight_failures=bool(row.retry_preflight_failures),
        schedule_enabled=row.schedule_enabled,
        schedule_hours_limited=row.schedule_hours_limited,
        schedule_days=row.schedule_days,
        schedule_start=row.schedule_start,
        schedule_end=row.schedule_end,
        max_concurrent_files=row.max_concurrent_files,
        priority=row.priority,
        rule_set_id=row.rule_set_id,
        manager_connection_ids=list(manager_connection_ids_for(db, row)),
        discovered_from_connection_id=row.discovered_from_connection_id,
        discovered_library_key=row.discovered_library_key,
        active_job_count=active_job_count_for_library(db, row),
        updated_at=row.updated_at,
    )


def _rule_set_out(db, row: RefinerRuleSetRow) -> RefinerRuleSetOut:
    return RefinerRuleSetOut(
        id=row.id,
        name=row.name,
        primary_audio_lang=row.primary_audio_lang,
        secondary_audio_lang=row.secondary_audio_lang,
        tertiary_audio_lang=row.tertiary_audio_lang,
        default_audio_slot=row.default_audio_slot,
        remove_commentary=row.remove_commentary,
        subtitle_mode=row.subtitle_mode,
        subtitle_langs_csv=row.subtitle_langs_csv,
        preserve_forced_subs=row.preserve_forced_subs,
        preserve_default_subs=row.preserve_default_subs,
        audio_preference_mode=row.audio_preference_mode,
        audio_sorters_json=row.audio_sorters_json or "",
        subtitle_sorters_json=row.subtitle_sorters_json or "",
        used_by_library_count=rule_set_usage_count(db, row),
        updated_at=row.updated_at,
    )


def _require_library(db: DbSessionDep, library_id: int) -> RefinerLibraryRow:
    row = db.get(RefinerLibraryRow, library_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That Refiner library does not exist.")
    return row


def _require_rule_set(db: DbSessionDep, rule_set_id: int) -> RefinerRuleSetRow:
    row = db.get(RefinerRuleSetRow, rule_set_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That Refiner rule set does not exist.")
    return row


@router.get("/refiner/libraries", response_model=list[RefinerLibraryOut])
def get_refiner_libraries(_user: UserPublicDep, db: DbSessionDep) -> list[RefinerLibraryOut]:
    """Every configured Refiner library, in display order."""

    return [_library_out(db, row) for row in list_libraries(db)]


@router.post("/refiner/libraries", response_model=RefinerLibraryOut, status_code=status.HTTP_201_CREATED)
def post_refiner_library(
    body: RefinerLibraryCreateIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerLibraryOut:
    """Add a Refiner library."""

    _verify_csrf(request, settings, body.csrf_token)
    try:
        row = create_library(db, body)
    except RefinerLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _library_out(db, row)


@router.get("/refiner/libraries/{library_id}", response_model=RefinerLibraryOut)
def get_refiner_library(
    _user: UserPublicDep,
    db: DbSessionDep,
    library_id: int = Path(ge=1),
) -> RefinerLibraryOut:
    return _library_out(db, _require_library(db, library_id))


@router.put("/refiner/libraries/{library_id}", response_model=RefinerLibraryOut)
def put_refiner_library(
    body: RefinerLibraryUpdateIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    library_id: int = Path(ge=1),
) -> RefinerLibraryOut:
    """Save a Refiner library. Edited whole, so a partial save cannot half-apply."""

    _verify_csrf(request, settings, body.csrf_token)
    row = _require_library(db, library_id)
    try:
        update_library(db, row, body)
    except RefinerLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _library_out(db, row)


@router.delete("/refiner/libraries/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_refiner_library(
    body: RefinerLibraryDeleteIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    library_id: int = Path(ge=1),
) -> None:
    """Remove a library. Refused while it still has queued or running work."""

    _verify_csrf(request, settings, body.csrf_token)
    row = _require_library(db, library_id)
    try:
        delete_library(db, row)
    except RefinerLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()


@router.post("/refiner/libraries/reorder", response_model=list[RefinerLibraryOut])
def post_refiner_libraries_reorder(
    body: RefinerLibraryReorderIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> list[RefinerLibraryOut]:
    """Set display order. Order decides which library a scope-only payload resolves to."""

    _verify_csrf(request, settings, body.csrf_token)
    try:
        rows = reorder_libraries(db, list(body.library_ids_in_order))
    except RefinerLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return [_library_out(db, row) for row in rows]


@router.get("/refiner/rule-sets", response_model=list[RefinerRuleSetOut])
def get_refiner_rule_sets(_user: UserPublicDep, db: DbSessionDep) -> list[RefinerRuleSetOut]:
    rows = db.scalars(select(RefinerRuleSetRow).order_by(RefinerRuleSetRow.id))
    return [_rule_set_out(db, row) for row in rows]


@router.post("/refiner/rule-sets", response_model=RefinerRuleSetOut, status_code=status.HTTP_201_CREATED)
def post_refiner_rule_set(
    body: RefinerRuleSetIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> RefinerRuleSetOut:
    _verify_csrf(request, settings, body.csrf_token)
    try:
        row = create_rule_set(db, body)
    except RefinerLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _rule_set_out(db, row)


@router.put("/refiner/rule-sets/{rule_set_id}", response_model=RefinerRuleSetOut)
def put_refiner_rule_set(
    body: RefinerRuleSetIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    rule_set_id: int = Path(ge=1),
) -> RefinerRuleSetOut:
    _verify_csrf(request, settings, body.csrf_token)
    row = _require_rule_set(db, rule_set_id)
    try:
        update_rule_set(db, row, body)
    except RefinerLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _rule_set_out(db, row)


@router.delete("/refiner/rule-sets/{rule_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_refiner_rule_set(
    body: RefinerLibraryDeleteIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    rule_set_id: int = Path(ge=1),
) -> None:
    """Remove a rule set. Refused while a library still points at it."""

    _verify_csrf(request, settings, body.csrf_token)
    row = _require_rule_set(db, rule_set_id)
    try:
        delete_rule_set(db, row)
    except RefinerLibraryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()


def _require_connection(db: DbSessionDep, connection_id: int) -> MediaManagerConnectionRow:
    row = db.get(MediaManagerConnectionRow, connection_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That media manager connection does not exist."
        )
    return row


@router.get(
    "/refiner/libraries/discover/{connection_id}",
    response_model=list[DiscoverableLibraryOut],
)
def get_refiner_discoverable_libraries(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
) -> list[DiscoverableLibraryOut]:
    """What this manager says it looks after, and whether MediaMop already has it."""

    connection = _require_connection(db, connection_id)
    try:
        found = discoverable_libraries(db, settings, connection)
    except RefinerDiscoveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [DiscoverableLibraryOut(**vars(item)) for item in found]


@router.post(
    "/refiner/libraries/discover/{connection_id}/import",
    response_model=list[RefinerLibraryOut],
    status_code=status.HTTP_201_CREATED,
)
def post_refiner_import_libraries(
    body: RefinerLibraryImportIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
) -> list[RefinerLibraryOut]:
    """Create a Refiner library per selected manager library."""

    _verify_csrf(request, settings, body.csrf_token)
    connection = _require_connection(db, connection_id)
    try:
        created = import_libraries(db, settings, connection, keys=list(body.keys))
    except RefinerDiscoveryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return [_library_out(db, row) for row in created]


@router.get(
    "/refiner/libraries/discover/{connection_id}/drift",
    response_model=list[LibraryDriftOut],
)
def get_refiner_library_drift(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
) -> list[LibraryDriftOut]:
    """Differences between the manager and MediaMop. Reported only — nothing is applied."""

    connection = _require_connection(db, connection_id)
    try:
        drift = resync_drift(db, settings, connection)
    except RefinerDiscoveryError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [LibraryDriftOut(**vars(item)) for item in drift]


@router.post("/refiner/libraries/{library_id}/unlink", response_model=RefinerLibraryOut)
def post_refiner_library_unlink(
    body: RefinerLibraryDeleteIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    library_id: int = Path(ge=1),
) -> RefinerLibraryOut:
    """Forget where a library came from. The library itself is untouched."""

    _verify_csrf(request, settings, body.csrf_token)
    row = _require_library(db, library_id)
    unlink_library(db, row)
    db.commit()
    db.refresh(row)
    return _library_out(db, row)
