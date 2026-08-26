"""HTTP for media manager connections: ``/api/v1/media-managers/connections``.

One kinded resource replaces the two fixed panels that were
``/arr-library/arr-connection/radarr`` and ``.../sonarr``. Adding a manager is a POST,
not a schema change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Path, Request
from sqlalchemy import select
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.core.config import MediaMopSettings
from mediamop.platform.arr_library.arr_connection_crypto import decrypt_arr_api_key
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.media_managers.connection_model import (
    MediaManagerConnectionRow,
    MediaManagerSearchLaneRow,
)
from mediamop.platform.media_managers.connection_schemas import (
    MediaManagerConnectionCreateIn,
    MediaManagerConnectionDeleteIn,
    MediaManagerConnectionOut,
    MediaManagerConnectionTestIn,
    MediaManagerConnectionTestOut,
    MediaManagerConnectionUpdateIn,
    MediaManagerKind,
    MediaManagerSearchLaneIn,
    MediaManagerSearchLaneOut,
    MediaManagerWebhookSecretOut,
    SearchLane,
)
from mediamop.platform.media_managers.connection_service import (
    MediaManagerConnectionError,
    create_connection,
    get_connection,
    list_connections,
    rotate_webhook_secret,
    update_connection,
)
from mediamop.platform.media_managers.manager_http import (
    MediaManagerHttpClient,
    MediaManagerHttpError,
)
from mediamop.platform.media_managers.schedule_csv_validate import (
    normalize_hhmm,
    validate_schedule_days_csv,
)

router = APIRouter(tags=["media-managers"])

_TEST_TIMEOUT_SECONDS = 15.0


def _verify_csrf(request: Request, settings: MediaMopSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )


def _webhook_url_path(row: MediaManagerConnectionRow) -> str:
    return f"/api/v1/intake/webhook/{row.kind}"


def _to_out(row: MediaManagerConnectionRow) -> MediaManagerConnectionOut:
    return MediaManagerConnectionOut(
        id=row.id,
        # Stored as text; every write path runs it through _validate_kind first.
        kind=cast(MediaManagerKind, row.kind),
        name=row.name,
        enabled=row.enabled,
        base_url=row.base_url,
        api_key_is_saved=bool(row.api_key_ciphertext),
        webhook_secret_is_set=bool(row.webhook_secret_ciphertext),
        webhook_url_path=_webhook_url_path(row),
        last_test_ok=row.last_connection_test_ok,
        last_test_at=row.last_connection_test_at,
        last_test_detail=row.last_connection_test_detail,
        lanes=[MediaManagerSearchLaneOut.model_validate(lane) for lane in sorted(row.lanes, key=lambda x: x.lane)],
    )


def _require(db: DbSessionDep, connection_id: int) -> MediaManagerConnectionRow:
    row = get_connection(db, connection_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That media manager connection does not exist."
        )
    return row


@router.get("/media-managers/connections", response_model=list[MediaManagerConnectionOut])
def get_media_manager_connections(_user: RequireOperatorDep, db: DbSessionDep) -> list[MediaManagerConnectionOut]:
    """Every configured media manager."""

    return [_to_out(row) for row in list_connections(db)]


@router.post(
    "/media-managers/connections",
    response_model=MediaManagerConnectionOut,
    status_code=status.HTTP_201_CREATED,
)
def post_media_manager_connection(
    body: MediaManagerConnectionCreateIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> MediaManagerConnectionOut:
    """Add a media manager."""

    _verify_csrf(request, settings, body.csrf_token)
    try:
        row = create_connection(
            db,
            settings,
            kind=body.kind,
            name=body.name,
            base_url=body.base_url,
            api_key=body.api_key or None,
            enabled=body.enabled,
        )
    except MediaManagerConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/media-managers/connections/{connection_id}", response_model=MediaManagerConnectionOut)
def get_media_manager_connection(
    _user: RequireOperatorDep,
    db: DbSessionDep,
    connection_id: int = Path(ge=1),
) -> MediaManagerConnectionOut:
    return _to_out(_require(db, connection_id))


@router.put("/media-managers/connections/{connection_id}", response_model=MediaManagerConnectionOut)
def put_media_manager_connection(
    body: MediaManagerConnectionUpdateIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
) -> MediaManagerConnectionOut:
    """Change a media manager. Omitting ``api_key`` leaves the saved key alone."""

    _verify_csrf(request, settings, body.csrf_token)
    row = _require(db, connection_id)
    try:
        update_connection(
            db,
            settings,
            row,
            name=body.name,
            base_url=body.base_url,
            api_key=body.api_key,
            enabled=body.enabled,
        )
    except MediaManagerConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/media-managers/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_manager_connection(
    body: MediaManagerConnectionDeleteIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
) -> None:
    _verify_csrf(request, settings, body.csrf_token)
    row = _require(db, connection_id)
    db.delete(row)
    db.commit()


@router.post(
    "/media-managers/connections/{connection_id}/webhook-secret",
    response_model=MediaManagerWebhookSecretOut,
)
def post_media_manager_webhook_secret(
    body: MediaManagerConnectionTestIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
) -> MediaManagerWebhookSecretOut:
    """Generate a fresh inbound secret for this manager. Shown once, stored encrypted."""

    _verify_csrf(request, settings, body.csrf_token)
    row = _require(db, connection_id)
    plaintext = rotate_webhook_secret(db, settings, row)
    db.commit()
    return MediaManagerWebhookSecretOut(
        connection_id=row.id,
        webhook_secret=plaintext,
        webhook_url_path=_webhook_url_path(row),
    )


@router.put(
    "/media-managers/connections/{connection_id}/lanes/{lane}",
    response_model=MediaManagerSearchLaneOut,
)
def put_media_manager_lane(
    body: MediaManagerSearchLaneIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
    lane: SearchLane = Path(),
) -> MediaManagerSearchLaneOut:
    """Save one automatic search lane for one manager."""

    _verify_csrf(request, settings, body.csrf_token)
    _require(db, connection_id)
    row = db.scalars(
        select(MediaManagerSearchLaneRow)
        .where(MediaManagerSearchLaneRow.connection_id == connection_id)
        .where(MediaManagerSearchLaneRow.lane == lane)
    ).first()
    if row is None:
        row = MediaManagerSearchLaneRow(connection_id=connection_id, lane=lane)
        db.add(row)

    try:
        schedule_days = validate_schedule_days_csv(body.schedule_days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    row.enabled = body.enabled
    row.max_items_per_run = body.max_items_per_run
    row.retry_delay_minutes = body.retry_delay_minutes
    row.schedule_enabled = body.schedule_enabled
    row.schedule_days = schedule_days
    # Same normalisation the previous settings screen applied, so a half-typed time
    # becomes a sane one rather than being stored and silently ignored later.
    row.schedule_start = normalize_hhmm(body.schedule_start, fallback="00:00")
    row.schedule_end = normalize_hhmm(body.schedule_end, fallback="23:59")
    row.schedule_interval_seconds = body.schedule_interval_seconds
    db.commit()
    db.refresh(row)
    return MediaManagerSearchLaneOut.model_validate(row)


# Where each kind answers a liveness check. Radarr and Sonarr share the arr v3 shape;
# Deluno and anything speaking the native payload publish the integration health route.
_HEALTH_PATHS: dict[str, str] = {
    "radarr": "/api/v3/system/status",
    "sonarr": "/api/v3/system/status",
    "deluno": "/api/integrations/external/health",
    "native": "/api/integrations/external/health",
}


def _probe(name: str, kind: str, base_url: str, api_key: str | None) -> tuple[bool, str]:
    """Ask a manager whether it is there, and say what happened in plain words.

    These strings go straight onto a settings card, so they name the thing the
    operator recognises and, when something is wrong, what to go and check.
    """

    path = _HEALTH_PATHS.get(kind, "/api/integrations/external/health")
    try:
        client = MediaManagerHttpClient(base_url, api_key or "", timeout_seconds=_TEST_TIMEOUT_SECONDS)
        client.health_ok(path)
    except MediaManagerHttpError as exc:
        detail = str(exc)
        if "HTTP 401" in detail or "HTTP 403" in detail:
            return False, f"MediaMop reached {name}, but the API key was refused. Check the key and save it again."
        return False, (
            f"MediaMop reached {name} but did not get the answer it expected. "
            "Check the address points at the app itself, not a page inside it."
        )
    except OSError:
        return False, (
            f"MediaMop could not reach {name} at {base_url}. "
            "Check the address is right, and that the app is running and reachable from this machine."
        )
    return True, f"Connected. MediaMop can reach {name}."


@router.post(
    "/media-managers/connections/{connection_id}/test",
    response_model=MediaManagerConnectionTestOut,
)
def post_media_manager_connection_test(
    body: MediaManagerConnectionTestIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    connection_id: int = Path(ge=1),
) -> MediaManagerConnectionTestOut:
    """Check the saved address and key actually reach the manager."""

    _verify_csrf(request, settings, body.csrf_token)
    row = _require(db, connection_id)
    checked_at = datetime.now(UTC)

    if not (row.base_url or "").strip():
        ok, detail = False, "Add the address where this app can be reached, then test again."
    else:
        api_key = decrypt_arr_api_key(settings, row.api_key_ciphertext) if row.api_key_ciphertext else None
        ok, detail = _probe(row.name, row.kind, row.base_url, api_key)

    row.last_connection_test_ok = ok
    row.last_connection_test_at = checked_at
    row.last_connection_test_detail = detail
    db.commit()
    return MediaManagerConnectionTestOut(connection_id=row.id, ok=ok, detail=detail, checked_at=checked_at)
