"""Read-only Activity feed API + narrow SSE freshness stream."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.platform.activity.live_stream import activity_latest_notifier
from mediamop.platform.activity.schemas import ActivityEventItemOut, ActivityRecentOut
from mediamop.platform.activity.service import (
    RECENT_DEFAULT_LIMIT,
    count_activity_events,
    count_system_activity_events,
    get_latest_activity_event_id,
    list_recent_activity_events,
)
from mediamop.platform.auth import service as auth_service
from mediamop.platform.auth.deps_auth import UserPublicDep
from mediamop.platform.auth.models import UserRole

_VALID_SESSION_ROLES = frozenset(
    {UserRole.admin.value, UserRole.operator.value, UserRole.viewer.value},
)
_STREAM_RETRY_MS = 5000
_STREAM_POLL_SECONDS = 2.0
_STREAM_KEEPALIVE_EVERY_POLLS = 8

router = APIRouter(prefix="/activity", tags=["activity"])


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
    )
    return ActivityRecentOut(
        items=[ActivityEventItemOut.model_validate(r) for r in rows],
        total=count_activity_events(
            db,
            module=module,
            event_type=event_type,
            search=search,
            date_from=parsed_from,
            date_to=parsed_to,
        ),
        system_events=count_system_activity_events(
            db,
            event_type=event_type,
            search=search,
            date_from=parsed_from,
            date_to=parsed_to,
        ),
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
        assert isinstance(db, Session)
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
        assert isinstance(db, Session)
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
        latest_id = read_latest_id()
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
