"""Shared helpers for DB-backed API tests (auth, dashboard, activity)."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.auth.models import User, UserSession, UserRole
from mediamop.platform.auth.password import hash_password


def reset_user_tables() -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.commit()


def seed_admin_user() -> None:
    reset_user_tables()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.add(
            User(
                username="alice",
                password_hash=hash_password("test-password-strong"),
                role="admin",
                is_active=True,
            )
        )
        db.commit()


def seed_viewer_user() -> None:
    reset_user_tables()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.add(
            User(
                username="bob",
                password_hash=hash_password("viewer-password-here"),
                role=UserRole.viewer.value,
                is_active=True,
            )
        )
        db.commit()


def csrf(client: TestClient) -> str:
    r = client.get("/api/v1/auth/csrf")
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def trusted_browser_origin_headers() -> dict[str, str]:
    settings = MediaMopSettings.load()
    trusted = settings.trusted_browser_origins
    if not trusted:
        return {}
    return {"Origin": trusted[0].rstrip("/")}


def auth_post(
    client: TestClient,
    path: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
):
    merged = {**trusted_browser_origin_headers(), **(headers or {})}
    kw: dict[str, object] = {"headers": merged}
    if json is not None:
        kw["json"] = json
    return client.post(path, **kw)


def auth_patch(
    client: TestClient,
    path: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
):
    merged = {**trusted_browser_origin_headers(), **(headers or {})}
    kw: dict[str, object] = {"headers": merged}
    if json is not None:
        kw["json"] = json
    return client.patch(path, **kw)


def auth_put(
    client: TestClient,
    path: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
):
    merged = {**trusted_browser_origin_headers(), **(headers or {})}
    kw: dict[str, object] = {"headers": merged}
    if json is not None:
        kw["json"] = json
    return client.put(path, **kw)
