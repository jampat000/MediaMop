"""Read-only Activity feed API + narrow SSE freshness stream."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.responses import Response, StreamingResponse

from weir.api.deps import DbSessionDep, SettingsDep
from weir.platform.activity.live_stream import activity_latest_notifier
from weir.platform.activity.schemas import (
    ActivityEventItemOut,
    ActivityFileHistoryCountOut,
    ActivityFileHistoryRemoveIn,
    ActivityFileHistoryRemoveOut,
    ActivityRecentOut,
)
from weir.platform.activity.service import (
    EXPORT_MAX_ROWS,
    RECENT_DEFAULT_LIMIT,
    count_activity_events,
    count_file_activity_history,
    count_system_activity_events,
    delete_file_activity_history,
    get_latest_activity_event_id,
    get_oldest_activity_event_at,
    list_activity_events_for_export,
    list_recent_activity_events,
)
from weir.platform.auth import service as auth_service
from weir.platform.auth.authorization import RequireOperatorDep
from weir.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from weir.platform.auth.deps_auth import UserPublicDep
from weir.platform.auth.models import UserRole
from weir.platform.suite_settings.service import ensure_suite_settings_row
from weir.refiner.refiner_file_log_model import RefinerFileLogRow

_VALID_SESSION_ROLES = frozenset(
    {UserRole.admin.value, UserRole.operator.value, UserRole.viewer.value},
)
_STREAM_RETRY_MS = 5000
_STREAM_POLL_SECONDS = 2.0
_STREAM_KEEPALIVE_EVERY_POLLS = 8

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/activity", tags=["activity"])


def _parse_when(raw: str | None, name: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {name}.") from exc


@router.get("/recent", response_model=ActivityRecentOut)
def get_activity_recent(
    _user: UserPublicDep,
    db: DbSessionDep,
    limit: int = Query(default=RECENT_DEFAULT_LIMIT, ge=1, le=100),
    module: str | None = Query(default=None, min_length=1, max_length=32),
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    search: str | None = Query(default=None, min_length=1, max_length=200),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    before_id: int | None = Query(default=None, ge=1),
    trigger: str | None = Query(default=None, min_length=1, max_length=32),
    result: str | None = Query(default=None, min_length=1, max_length=16),
    library_id: int | None = Query(default=None, ge=1),
    file: str | None = Query(default=None, min_length=1, max_length=2000),
) -> ActivityRecentOut:
    """Recent persisted events, newest first — snapshot only (pagination-style read; not a control plane)."""

    parsed_from = None
    parsed_to = None
    if date_from:
        try:
            parsed_from = datetime.fromisoformat(date_from)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date_from.") from exc
    if date_to:
        try:
            parsed_to = datetime.fromisoformat(date_to)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date_to.") from exc

    rows = list_recent_activity_events(
        db,
        limit=limit,
        module=module,
        event_type=event_type,
        search=search,
        date_from=parsed_from,
        date_to=parsed_to,
        before_id=before_id,
        trigger=trigger,
        result=result,
        library_id=library_id,
        file=file,
    )
    total = count_activity_events(
        db,
        module=module,
        event_type=event_type,
        search=search,
        date_from=parsed_from,
        date_to=parsed_to,
        trigger=trigger,
        result=result,
        library_id=library_id,
        file=file,
    )
    return ActivityRecentOut(
        items=[ActivityEventItemOut.model_validate(r) for r in rows],
        # A concurrent insert/delete can make the two reads observe different
        # moments. Never return a total smaller than the rows in this page.
        total=max(total, len(rows)),
        system_events=count_system_activity_events(
            db,
            event_type=event_type,
            search=search,
            date_from=parsed_from,
            date_to=parsed_to,
        ),
        has_more=total > len(rows),
        retention_days=int(ensure_suite_settings_row(db).activity_retention_days),
        oldest_event_at=get_oldest_activity_event_at(db),
    )


def _get_session_factory_or_503(request: Request):
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database session factory not initialized (app lifespan did not start cleanly).",
        )
    return factory


def _authenticate_stream_user(request: Request, settings) -> None:
    """Authenticate once with a short-lived DB session; never hold it for stream lifetime."""

    factory = _get_session_factory_or_503(request)
    raw = (request.cookies.get(settings.session_cookie_name) or "").strip() or None
    with factory() as db:
        if not isinstance(db, Session):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database session is unavailable for the activity stream.",
            )
        pair = auth_service.load_valid_session_for_request(db, raw, settings)
        if pair is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
        _row, user = pair
        if user.role not in _VALID_SESSION_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid account role.")
        # Avoid SQLite commit churn when load_valid_session did not persist (throttled last_seen).
        if db.dirty or db.new or db.deleted:
            db.commit()


def _latest_event_id_once(request: Request) -> int | None:
    factory = _get_session_factory_or_503(request)
    with factory() as db:
        if not isinstance(db, Session):
            raise RuntimeError("Activity stream database session is unavailable.")
        return get_latest_activity_event_id(db)


def _sse_event(*, event: str, data: dict[str, int]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def iter_activity_latest_sse(
    *,
    read_latest_id: Callable[[], int | None],
    is_disconnected: Callable[[], Awaitable[bool]],
    poll_seconds: float = _STREAM_POLL_SECONDS,
    keepalive_every_polls: int = _STREAM_KEEPALIVE_EVERY_POLLS,
) -> AsyncGenerator[str, None]:
    """Narrow activity freshness SSE stream: emits only latest id changes + keepalives."""

    last_sent_id: int | None = None
    _latest_id, last_seen_version = activity_latest_notifier.snapshot()
    polls_since_keepalive = 0
    yield f"retry: {_STREAM_RETRY_MS}\n\n"
    while True:
        if await is_disconnected():
            break
        try:
            latest_id = read_latest_id()
        except Exception:
            logger.warning("SSE activity stream: read_latest_id failed, retrying after back-off")
            await asyncio.sleep(poll_seconds)
            continue
        if latest_id is not None and latest_id != last_sent_id:
            last_sent_id = latest_id
            _notifier_latest_id, notifier_version = activity_latest_notifier.snapshot()
            last_seen_version = max(last_seen_version, notifier_version)
            yield _sse_event(
                event="activity.latest",
                data={"latest_event_id": latest_id, "activity_revision": last_seen_version},
            )
            polls_since_keepalive = 0
            continue
        changed = await activity_latest_notifier.wait_for_change(last_seen_version, timeout=poll_seconds)
        if changed is not None:
            latest_id, last_seen_version = changed
            if latest_id is not None:
                last_sent_id = latest_id
                yield _sse_event(
                    event="activity.latest",
                    data={"latest_event_id": latest_id, "activity_revision": last_seen_version},
                )
                polls_since_keepalive = 0
                continue
        polls_since_keepalive += 1
        if polls_since_keepalive >= keepalive_every_polls:
            yield ": keepalive\n\n"
            polls_since_keepalive = 0


@router.get("/stream")
async def get_activity_stream(
    request: Request,
    settings: SettingsDep,
) -> StreamingResponse:
    """Authenticated SSE freshness signal for activity-backed pages."""

    _authenticate_stream_user(request, settings)

    return StreamingResponse(
        iter_activity_latest_sse(
            read_latest_id=lambda: _latest_event_id_once(request),
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


_EXPORT_COLUMNS = (
    "id",
    "created_at",
    "module",
    "event_type",
    "trigger",
    "result",
    "library_id",
    "relative_path",
    "title",
    "detail",
)


@router.get("/export")
def get_activity_export(
    _user: UserPublicDep,
    db: DbSessionDep,
    export_format: str = Query(default="csv", alias="format", pattern="^(csv|json)$"),
    module: str | None = Query(default=None, min_length=1, max_length=32),
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    search: str | None = Query(default=None, min_length=1, max_length=200),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    trigger: str | None = Query(default=None, min_length=1, max_length=32),
    result: str | None = Query(default=None, min_length=1, max_length=16),
    library_id: int | None = Query(default=None, ge=1),
    file: str | None = Query(default=None, min_length=1, max_length=2000),
) -> Response:
    """The filtered history as a file, oldest first — for your records or a bug report."""

    rows = list_activity_events_for_export(
        db,
        module=module,
        event_type=event_type,
        search=search,
        date_from=_parse_when(date_from, "date_from"),
        date_to=_parse_when(date_to, "date_to"),
        trigger=trigger,
        result=result,
        library_id=library_id,
        file=file,
    )
    records = [
        {
            column: (getattr(row, column).isoformat() if column == "created_at" else getattr(row, column))
            for column in _EXPORT_COLUMNS
        }
        for row in rows
    ]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    headers = {"X-Weir-Export-Limit": str(EXPORT_MAX_ROWS), "X-Weir-Export-Rows": str(len(records))}
    if export_format == "json":
        headers["Content-Disposition"] = f'attachment; filename="weir-activity-{stamp}.json"'
        return Response(
            json.dumps(records, ensure_ascii=False, indent=2), media_type="application/json", headers=headers
        )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(_EXPORT_COLUMNS))
    writer.writeheader()
    writer.writerows(records)
    headers["Content-Disposition"] = f'attachment; filename="weir-activity-{stamp}.csv"'
    return Response(buffer.getvalue(), media_type="text/csv; charset=utf-8", headers=headers)


def _processing_records(db: Session, *, library_id: int | None, relative_path: str):
    stmt = select(RefinerFileLogRow).where(RefinerFileLogRow.relative_path == relative_path)
    if library_id is not None:
        stmt = stmt.where(RefinerFileLogRow.library_id == library_id)
    return stmt


@router.get("/file-history", response_model=ActivityFileHistoryCountOut)
def get_activity_file_history(
    _user: UserPublicDep,
    db: DbSessionDep,
    relative_path: str = Query(..., min_length=1, max_length=2000),
    library_id: int | None = Query(default=None, ge=1),
) -> ActivityFileHistoryCountOut:
    """What removing one file's history would delete — shown before anyone confirms."""

    path = relative_path.strip()
    events = count_file_activity_history(db, library_id=library_id, relative_path=path)
    records_stmt = _processing_records(db, library_id=library_id, relative_path=path)
    records = int(db.scalar(select(func.count()).select_from(records_stmt.subquery())) or 0)
    return ActivityFileHistoryCountOut(
        relative_path=path,
        activity_events=events,
        processing_records=records,
        message=(
            f"This removes {events} Activity event(s) and {records} processing record(s) about {path}. "
            "It does not touch the file itself, its current status on the Files screen, or anything else's history."
        ),
    )


@router.post("/file-history/remove", response_model=ActivityFileHistoryRemoveOut)
def post_activity_file_history_remove(
    body: ActivityFileHistoryRemoveIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> ActivityFileHistoryRemoveOut:
    """Delete one file's history. Irreversible, history only: no media file is ever touched."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your confirmation token expired. Refresh the page and try again.",
        )
    path = body.relative_path.strip()
    events = delete_file_activity_history(db, library_id=body.library_id, relative_path=path)
    stmt = delete(RefinerFileLogRow).where(RefinerFileLogRow.relative_path == path)
    if body.library_id is not None:
        stmt = stmt.where(RefinerFileLogRow.library_id == body.library_id)
    records = int(db.execute(stmt).rowcount or 0)  # type: ignore[attr-defined]
    db.commit()
    return ActivityFileHistoryRemoveOut(
        relative_path=path, activity_events_deleted=events, processing_records_deleted=records
    )
