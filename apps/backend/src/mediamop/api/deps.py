"""Shared FastAPI dependencies for the MediaMop API.

Expand here for shared dependencies. Auth rate limits and CSRF live under ``platform/auth/`` (Phase 6).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings


def get_settings(request: Request) -> MediaMopSettings:
    """Settings loaded during lifespan and stored on ``app.state.settings``."""
    return request.app.state.settings


SettingsDep = Annotated[MediaMopSettings, Depends(get_settings)]


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Request-scoped synchronous ORM session — close after the request.

    Raises ``503`` when no database is configured (intentional spine posture: PostgreSQL is
    required for real installs; CI and local smoke still run ``/health`` without a URL).
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured (set MEDIAMOP_DATABASE_URL).",
        )
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSessionDep = Annotated[Session, Depends(get_db_session)]
