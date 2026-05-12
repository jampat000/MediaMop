"""Map database errors from ``GET /auth/bootstrap/status`` to HTTP expectations.

Bootstrap status is a first-run probe: almost any database failure should surface as **503**
with operator-facing copy (migrations, ``MEDIAMOP_HOME``), not **500**.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError


def _is_sqlite_schema_missing_message(text: str) -> bool:
    """SQLite and SQLAlchemy often wrap ``no such table`` as :class:`OperationalError`."""

    lower = text.lower()
    if "no such table" in lower:
        return True
    return "no such column" in lower


def _is_missing_relation_or_schema(exc: ProgrammingError) -> bool:
    """Detect undefined table/relation — typical when Alembic has not been run."""

    orig = getattr(exc, "orig", None)
    if orig is not None:
        pgcode = getattr(orig, "pgcode", None)
        if pgcode == "42P01":
            return True
    msg = str(exc).lower()
    if "no such table" in msg:
        return True
    return "does not exist" in msg and "relation" in msg


_SCHEMA_NOT_READY = "Local SQLite schema is not ready (run alembic upgrade head)."
_DB_UNAVAILABLE = "SQLite database unavailable or cannot be opened (check MEDIAMOP_HOME and MEDIAMOP_DB_PATH)."
_QUERY_FAILED = (
    "Database query failed while checking bootstrap status. "
    "See backend logs, run alembic upgrade head, and verify MEDIAMOP_HOME / MEDIAMOP_DB_PATH."
)


def raise_http_for_bootstrap_status_db(exc: OperationalError | ProgrammingError) -> None:
    """Raise :class:`HTTPException` (503) for known DB/schema/connectivity failures."""

    if isinstance(exc, OperationalError):
        if _is_sqlite_schema_missing_message(str(exc)):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=_SCHEMA_NOT_READY,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_DB_UNAVAILABLE,
        ) from exc
    if _is_missing_relation_or_schema(exc):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_SCHEMA_NOT_READY,
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=_QUERY_FAILED,
    ) from exc


def raise_http_for_bootstrap_status_sqlalchemy(exc: SQLAlchemyError) -> None:
    """Map any ORM/DBAPI failure on this read-only path to **503** (never surprise **500**)."""

    if isinstance(exc, (OperationalError, ProgrammingError)):
        raise_http_for_bootstrap_status_db(exc)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=_QUERY_FAILED,
    ) from exc
