"""HTTP tests: GET bootstrap/status maps DB errors to HTTP status (DB session mocked).

Uses dependency override for the DB session so ``bootstrap_allowed`` is exercised via monkeypatch
without a live database (contract tests only).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError
from starlette.testclient import TestClient

from weir.api.deps import get_db_session
from weir.api.factory import create_app
from weir.platform.auth import bootstrap as bootstrap_service


@pytest.fixture
def client_bootstrap_status(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "weir.core.config._load_backend_dotenv_if_present",
        lambda: None,
    )
    monkeypatch.setenv("WEIR_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    app = create_app()

    mock_session = MagicMock()

    def _override_db():
        yield mock_session

    app.dependency_overrides[get_db_session] = _override_db
    try:
        # DB errors map to HTTP 503 on this endpoint (never surprise 500 from SQLAlchemy).
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


def test_bootstrap_status_unexpected_programming_returns_503(
    client_bootstrap_status: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_db: object) -> bool:
        raise ProgrammingError("SELECT", {}, Exception("syntax error near unexpected"))

    monkeypatch.setattr(bootstrap_service, "bootstrap_allowed", boom)
    r = client_bootstrap_status.get("/api/v1/auth/bootstrap/status")
    assert r.status_code == 503


def test_bootstrap_status_non_sqlalchemy_error_returns_503(
    client_bootstrap_status: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: never HTTP 500 on this guest-first path (map unknown failures to 503)."""

    def boom(_db: object) -> bool:
        raise RuntimeError("unexpected ORM state")

    monkeypatch.setattr(bootstrap_service, "bootstrap_allowed", boom)
    r = client_bootstrap_status.get("/api/v1/auth/bootstrap/status")
    assert r.status_code == 503
    assert isinstance(r.json().get("detail"), str) and len(r.json()["detail"]) > 10
