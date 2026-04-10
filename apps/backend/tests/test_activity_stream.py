"""Activity SSE stream tests (Stage 8 Pass 3) — SQLite (session ``MEDIAMOP_HOME``)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.api.deps import get_db_session
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity import service as activity_service
from mediamop.platform.activity.router import get_activity_stream, iter_activity_latest_sse
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _seed_activity_row(*, title: str) -> int:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        assert isinstance(db, Session)
        row = activity_service.record_activity_event(
            db,
            event_type=activity_constants.AUTH_LOGIN_SUCCEEDED,
            module="auth",
            title=title,
            detail="alice",
        )
        db.commit()
        return int(row.id)


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": tok,
        },
    )
    assert r.status_code == 200, r.text


def test_activity_stream_requires_authentication(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/activity/stream")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_activity_stream_authenticated_emits_latest_format(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    _seed_activity_row(title="SSE test row")
    settings = MediaMopSettings.load()
    cookie_name = settings.session_cookie_name
    raw = client_with_admin.cookies.get(cookie_name)
    assert raw is not None

    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    app = SimpleNamespace(state=SimpleNamespace(session_factory=fac))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/activity/stream",
        "headers": [(b"cookie", f"{cookie_name}={raw}".encode("utf-8"))],
        "app": app,
    }

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(scope, _receive)
    resp = await get_activity_stream(req, settings)
    assert resp.status_code == 200
    assert resp.media_type == "text/event-stream"


@pytest.mark.anyio
async def test_activity_stream_generator_emits_expected_payload_for_newer_id() -> None:
    values = iter([10, 10, 11, 11])
    checks = {"n": 0}

    async def _is_disconnected() -> bool:
        checks["n"] += 1
        return checks["n"] > 4

    gen = iter_activity_latest_sse(
        read_latest_id=lambda: next(values, 11),
        is_disconnected=_is_disconnected,
        poll_seconds=0.0,
        keepalive_every_polls=100,
    )
    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)

    merged = "".join(chunks)
    assert "event: activity.latest" in merged
    assert 'data: {"latest_event_id":10}' in merged
    assert 'data: {"latest_event_id":11}' in merged


def test_activity_stream_does_not_depend_on_request_db_dependency(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    app = create_app()
    stream_route = next(r for r in app.routes if getattr(r, "path", "") == "/api/v1/activity/stream")
    dep_calls = {d.call for d in stream_route.dependant.dependencies}
    assert get_db_session not in dep_calls
