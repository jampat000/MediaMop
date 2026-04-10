"""Unit tests for bootstrap status DB error → HTTP mapping (no database required)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError, ProgrammingError

from mediamop.platform.auth.bootstrap_status_db import raise_http_for_bootstrap_status_db


def test_operational_error_becomes_503() -> None:
    with pytest.raises(HTTPException) as ei:
        raise_http_for_bootstrap_status_db(
            OperationalError("SELECT 1", {}, Exception("connection refused")),
        )
    assert ei.value.status_code == 503
    assert "unavailable" in ei.value.detail.lower()


def test_programming_error_undefined_table_pgcode_becomes_503() -> None:
    class _PgOrig:
        pgcode = "42P01"

    with pytest.raises(HTTPException) as ei:
        raise_http_for_bootstrap_status_db(ProgrammingError("x", {}, _PgOrig()))
    assert ei.value.status_code == 503
    assert "schema" in ei.value.detail.lower()


def test_programming_error_missing_relation_message_becomes_503() -> None:
    exc = ProgrammingError(
        "statement",
        {},
        Exception('relation "users" does not exist'),
    )
    with pytest.raises(HTTPException) as ei:
        raise_http_for_bootstrap_status_db(exc)
    assert ei.value.status_code == 503


def test_programming_error_no_such_table_sqlite_message_becomes_503() -> None:
    exc = ProgrammingError(
        "statement",
        {},
        Exception("no such table: users"),
    )
    with pytest.raises(HTTPException) as ei:
        raise_http_for_bootstrap_status_db(exc)
    assert ei.value.status_code == 503


def test_programming_error_unexpected_reraises() -> None:
    exc = ProgrammingError("statement", {}, Exception("invalid syntax near foo"))
    with pytest.raises(ProgrammingError) as ei:
        raise_http_for_bootstrap_status_db(exc)
    assert ei.value is exc
