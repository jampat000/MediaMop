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
from mediamop.platform.jobs.worker_health import reset_worker_health_for_tests
from tests.integration_helpers import seed_admin_user, seed_viewer_user


@pytest.fixture(scope="session", autouse=True)
def _mediamop_sqlite_runtime(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Isolated SQLite under a temp ``MEDIAMOP_HOME`` + Alembic at head (shared session DB)."""

    home = tmp_path_factory.mktemp("mediamop_pytest_home")
    os.environ["MEDIAMOP_HOME"] = str(home)
    os.environ["MEDIAMOP_REFINER_WORKER_COUNT"] = "0"
    os.environ["MEDIAMOP_PRUNER_WORKER_COUNT"] = "0"
    os.environ["MEDIAMOP_PRUNER_PREVIEW_SCHEDULE_ENQUEUE_ENABLED"] = "0"
    os.environ["MEDIAMOP_PRUNER_APPLY_ENABLED"] = "0"
    os.environ["MEDIAMOP_SUBBER_WORKER_COUNT"] = "0"
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def ensure_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MEDIAMOP_SESSION_SECRET",
        os.environ.get("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!"),
    )


@pytest.fixture(autouse=True)
def _reset_worker_health_state() -> Iterator[None]:
    reset_worker_health_for_tests()
    yield
    reset_worker_health_for_tests()


@pytest.fixture
def client_with_admin() -> Iterator[TestClient]:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_viewer() -> Iterator[TestClient]:
    seed_viewer_user()
    app = create_app()
    with TestClient(app) as c:
        yield c
