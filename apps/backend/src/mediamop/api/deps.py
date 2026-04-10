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

    Raises ``503`` only when the app failed to attach a session factory during lifespan
    (abnormal: SQLite-first startup always builds an engine from ``MEDIAMOP_HOME`` /
    ``MEDIAMOP_DB_PATH``).
    """
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database session factory not initialized (app lifespan did not start cleanly).",
        )
    session = factory()
    try:
        yield session
        session.commit()
    except HTTPException:
        # Routes often raise HTTPException after intentional work (e.g. audit commit before 401).
        # Do not rollback here: after a successful in-route commit, rollback can upset the pool;
        # uncommitted work is cleared when the session is closed.
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSessionDep = Annotated[Session, Depends(get_db_session)]
