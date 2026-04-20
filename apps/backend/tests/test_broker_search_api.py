"""HTTP tests for ``/api/v1/broker/search``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from alembic import command
from alembic.config import Config
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.modules.broker.broker_result import BrokerResult
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_get, csrf, seed_admin_user, trusted_browser_origin_headers


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_broker_search_api")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def client_admin() -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _login(c: TestClient) -> None:
    tok = csrf(c)
    c.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
        headers=trusted_browser_origin_headers(),
    )


def test_search_returns_list_mocked(client_admin: TestClient) -> None:
    _login(client_admin)
    fake = [
        BrokerResult(
            title="A",
            url="http://a",
            magnet=None,
            size=1,
            seeders=1,
            leechers=None,
            protocol="torrent",
            indexer_slug="native__yts",
            categories=[2000],
            published_at=None,
            imdb_id=None,
            info_hash=None,
        ),
    ]
    with patch(
        "mediamop.modules.broker.broker_search_api.federated_search",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        r = auth_get(client_admin, "/api/v1/broker/search?q=test")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    assert data[0]["title"] == "A"


def test_search_type_tv_passes_media_type(client_admin: TestClient) -> None:
    _login(client_admin)
    with patch(
        "mediamop.modules.broker.broker_search_api.federated_search",
        new_callable=AsyncMock,
        return_value=[],
    ) as m:
        r = auth_get(client_admin, "/api/v1/broker/search?q=x&type=tv")
    assert r.status_code == 200, r.text
    assert m.await_args is not None
    assert m.await_args.kwargs["media_type"] == "tv"


def test_search_type_movie_passes_media_type(client_admin: TestClient) -> None:
    _login(client_admin)
    with patch(
        "mediamop.modules.broker.broker_search_api.federated_search",
        new_callable=AsyncMock,
        return_value=[],
    ) as m:
        r = auth_get(client_admin, "/api/v1/broker/search?q=x&type=movie")
    assert r.status_code == 200, r.text
    assert m.await_args.kwargs["media_type"] == "movie"


def test_search_empty_indexer_filter_returns_empty(client_admin: TestClient) -> None:
    _login(client_admin)
    r = auth_get(client_admin, "/api/v1/broker/search?q=test&indexers=")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_search_tv_before_movie_ordering_when_type_all(client_admin: TestClient) -> None:
    _login(client_admin)
    tv = BrokerResult(
        title="tvshow",
        url="u1",
        magnet=None,
        size=1,
        seeders=10,
        leechers=None,
        protocol="torrent",
        indexer_slug="a",
        categories=[5000],
        published_at=None,
        imdb_id=None,
        info_hash=None,
    )
    mv = BrokerResult(
        title="movie",
        url="u2",
        magnet=None,
        size=1,
        seeders=100,
        leechers=None,
        protocol="torrent",
        indexer_slug="b",
        categories=[2000],
        published_at=None,
        imdb_id=None,
        info_hash=None,
    )
    with patch(
        "mediamop.modules.broker.broker_search_api.federated_search",
        new_callable=AsyncMock,
        return_value=[mv, tv],
    ):
        r = auth_get(client_admin, "/api/v1/broker/search?q=test&type=all")
    assert r.status_code == 200, r.text
    titles = [x["title"] for x in r.json()]
    assert titles[0] == "tvshow"
    assert titles[1] == "movie"
