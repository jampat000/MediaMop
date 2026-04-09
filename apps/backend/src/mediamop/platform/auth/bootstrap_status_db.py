"""Map database errors from ``GET /auth/bootstrap/status`` to HTTP expectations.

Operational failures and missing schema (migrations not applied) are **503**.
Other :class:`sqlalchemy.exc.ProgrammingError` cases propagate as **500** (unexpected SQL bug).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import OperationalError, ProgrammingError


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
    if "does not exist" in msg and "relation" in msg:
        return True
    return False


def raise_http_for_bootstrap_status_db(exc: OperationalError | ProgrammingError) -> None:
    """Raise :class:`HTTPException` (503) or re-raise *exc* for a true 500."""

    if isinstance(exc, OperationalError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or connection failed.",
        ) from exc
    if _is_missing_relation_or_schema(exc):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database schema is not ready (run alembic upgrade head).",
        ) from exc
    raise exc
