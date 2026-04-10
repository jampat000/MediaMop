"""Read-only Activity feed API + narrow SSE freshness stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.platform.activity.schemas import ActivityEventItemOut, ActivityRecentOut
from mediamop.platform.activity.service import get_latest_activity_event_id, list_recent_activity_events
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
) -> ActivityRecentOut:
    """Recent persisted events, newest first — snapshot only (no live transport in Stage 8 Pass 1)."""

    rows = list_recent_activity_events(db)
    return ActivityRecentOut(
        items=[ActivityEventItemOut.model_validate(r) for r in rows],
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
    polls_since_keepalive = 0
    yield f"retry: {_STREAM_RETRY_MS}\n\n"
    while True:
        if await is_disconnected():
            break
        latest_id = read_latest_id()
        if latest_id is not None and latest_id != last_sent_id:
            last_sent_id = latest_id
            yield _sse_event(event="activity.latest", data={"latest_event_id": latest_id})
            polls_since_keepalive = 0
        else:
            polls_since_keepalive += 1
            if polls_since_keepalive >= keepalive_every_polls:
                yield ": keepalive\n\n"
                polls_since_keepalive = 0
        await asyncio.sleep(poll_seconds)


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
