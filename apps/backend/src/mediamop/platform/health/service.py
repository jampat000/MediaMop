"""Health domain logic — keep free of database and auth coupling."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from mediamop.platform.health.schemas import HealthResponse

logger = logging.getLogger(__name__)
_HEALTH_DB_BUSY_TIMEOUT_MS = 1000


def database_is_connected(app_state: Any) -> bool:
    factory = getattr(app_state, "session_factory", None)
    if factory is None:
        return False
    try:
        with factory() as session:
            conn = session.connection()
            previous_timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar_one_or_none()
            conn.exec_driver_sql(f"PRAGMA busy_timeout={_HEALTH_DB_BUSY_TIMEOUT_MS}")
            try:
                session.execute(text("SELECT 1"))
            finally:
                if previous_timeout is not None:
                    conn.exec_driver_sql(f"PRAGMA busy_timeout={int(previous_timeout)}")
        return True
    except Exception:
        logger.exception("health check failed: database connectivity probe failed")
        return False


def get_health(app_state: Any) -> HealthResponse:
    """Return process health plus basic local dependency checks."""

    db_ok = database_is_connected(app_state)
    return HealthResponse(
        status="ok" if db_ok else "unhealthy",
        dependencies={"database": "ok" if db_ok else "failed"},
    )
