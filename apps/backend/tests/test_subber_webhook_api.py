"""HTTP: Sonarr/Radarr Subber webhooks (no auth)."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.modules.subber.subber_jobs_model import SubberJob
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)


@pytest.fixture(autouse=True)
def _isolated_subber_webhook_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_subber_webhook")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_sonarr_non_download_ignored(client: TestClient) -> None:
    r = client.post(
        "/api/v1/subber/webhook/sonarr",
        json={"eventType": "Grab", "episodes": [{"id": 1}]},
    )
    assert r.status_code == 200
    assert r.json().get("status") == "ignored"


def test_sonarr_download_enqueues_job(client: TestClient) -> None:
    r = client.post(
        "/api/v1/subber/webhook/sonarr",
        json={
            "eventType": "Download",
            "series": {"title": "Test Show"},
            "episodes": [{"id": 9, "seasonNumber": 1, "episodeNumber": 2, "title": "Hello"}],
            "episodeFile": {"path": "/media/t/x.mkv"},
        },
    )
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
    settings = client.app.state.settings
    from mediamop.core.db import create_db_engine, create_session_factory

    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = db.scalars(select(SubberJob)).first()
        assert row is not None
        assert "webhook_import" in row.job_kind


def test_radarr_non_download_ignored(client: TestClient) -> None:
    r = client.post(
        "/api/v1/subber/webhook/radarr",
        json={"eventType": "Grab", "movie": {"id": 1}},
    )
    assert r.status_code == 200
    assert r.json().get("status") == "ignored"


def test_radarr_download_enqueues_job(client: TestClient) -> None:
    r = client.post(
        "/api/v1/subber/webhook/radarr",
        json={
            "eventType": "Download",
            "movie": {"id": 3, "title": "Film", "year": 2010},
            "movieFile": {"path": "/media/m/f.mkv"},
        },
    )
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
    settings = client.app.state.settings
    from mediamop.core.db import create_db_engine, create_session_factory

    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = db.scalars(select(SubberJob)).first()
        assert row is not None
        assert "webhook_import.movies" in row.job_kind
