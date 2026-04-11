"""Pytest fixtures for MediaMop backend integration tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.modules.fetcher.failed_import_queue_worker_runtime import build_failed_import_queue_worker_runtime_bundle
from tests.integration_helpers import seed_admin_user, seed_viewer_user


@pytest.fixture(scope="session", autouse=True)
def _mediamop_sqlite_runtime(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Isolated SQLite under a temp ``MEDIAMOP_HOME`` + Alembic at head (shared session DB)."""

    home = tmp_path_factory.mktemp("mediamop_pytest_home")
    os.environ["MEDIAMOP_HOME"] = str(home)
    # refiner_worker_count=0 disables in-process Refiner workers during pytest.
    # Avoids claiming synthetic ``pending`` rows during API tests (timing-sensitive on CI).
    os.environ["MEDIAMOP_REFINER_WORKER_COUNT"] = "0"
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def ensure_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MEDIAMOP_SESSION_SECRET",
        os.environ.get("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!"),
    )


@pytest.fixture
def client_with_admin() -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_viewer() -> TestClient:
    seed_viewer_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def failed_import_queue_worker_runtime_bundle():
    """Production Fetcher ports for Refiner failed-import handlers (tests that build production handlers)."""

    return build_failed_import_queue_worker_runtime_bundle()
