"""Shared FastAPI dependencies for the Weir API.

Expand here for shared dependencies. Auth rate limits and CSRF live under ``platform/auth/`` (Phase 6).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from weir.core.config import WeirSettings


def get_settings(request: Request) -> WeirSettings:
    """Settings loaded during lifespan and stored on ``app.state.settings``."""
    return request.app.state.settings


SettingsDep = Annotated[WeirSettings, Depends(get_settings)]


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Request-scoped synchronous ORM session — close after the request.

    Raises ``503`` only when the app failed to attach a session factory during lifespan
    (abnormal: SQLite-first startup always builds an engine from ``WEIR_HOME`` /
    ``WEIR_DB_PATH``).
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


# ``scope="function"``: commit before the response is sent. FastAPI's default ("request") runs this
# exit code after the response, so a client could be told 200 for a write that was not committed
# yet (or never, if the process stopped in between) and read stale data on its next request.
DbSessionDep = Annotated[Session, Depends(get_db_session, scope="function")]
