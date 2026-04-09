"""HTTP tests: GET bootstrap/status maps DB errors to HTTP status (no PostgreSQL required).

Uses dependency override for the DB session so ``bootstrap_allowed`` is exercised via monkeypatch
without a live database (contract tests only).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError
from starlette.testclient import TestClient

from mediamop.api.deps import get_db_session
from mediamop.api.factory import create_app
from mediamop.platform.auth import bootstrap as bootstrap_service


@pytest.fixture
def client_bootstrap_status(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "mediamop.core.config._load_backend_dotenv_if_present",
        lambda: None,
    )
    monkeypatch.delenv("MEDIAMOP_DATABASE_URL", raising=False)
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    app = create_app()

    mock_session = MagicMock()

    def _override_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = _override_db
    try:
        # Unexpected DB errors are re-raised from the router; return HTTP 500 instead of failing the client.
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_bootstrap_status_operational_error_returns_503(
    client_bootstrap_status: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_db: object) -> bool:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(bootstrap_service, "bootstrap_allowed", boom)
    r = client_bootstrap_status.get("/api/v1/auth/bootstrap/status")
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"].lower()


def test_bootstrap_status_missing_table_returns_503(
    client_bootstrap_status: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Orig:
        pgcode = "42P01"

    def boom(_db: object) -> bool:
        raise ProgrammingError("SELECT", {}, _Orig())

    monkeypatch.setattr(bootstrap_service, "bootstrap_allowed", boom)
    r = client_bootstrap_status.get("/api/v1/auth/bootstrap/status")
    assert r.status_code == 503
    assert "schema" in r.json()["detail"].lower()


def test_bootstrap_status_unexpected_programming_returns_500(
    client_bootstrap_status: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_db: object) -> bool:
        raise ProgrammingError("SELECT", {}, Exception("syntax error near unexpected"))

    monkeypatch.setattr(bootstrap_service, "bootstrap_allowed", boom)
    r = client_bootstrap_status.get("/api/v1/auth/bootstrap/status")
    assert r.status_code == 500
