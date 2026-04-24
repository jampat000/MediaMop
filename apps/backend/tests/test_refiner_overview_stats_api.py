from __future__ import annotations

import json

from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_refiner_overview_stats_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 401


def test_refiner_overview_stats_shape(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 30
    assert "files_processed" in body
    assert "files_failed" in body
    assert isinstance(body["files_failed"], int)
    assert "success_rate_percent" in body
    assert body["output_written_count"] == 0
    assert body["already_optimized_count"] == 0
    assert body["net_space_saved_bytes"] == 0
    assert body["net_space_saved_percent"] == 0.0


def test_refiner_overview_stats_aggregates_remux_savings(client_with_admin: TestClient) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(ActivityEvent))
        db.add_all(
            [
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Remux one",
                    detail=json.dumps(
                        {
                            "outcome": "live_output_written",
                            "source_size_bytes": 1_000,
                            "output_size_bytes": 700,
                        },
                        separators=(",", ":"),
                    ),
                ),
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Remux two",
                    detail=json.dumps(
                        {
                            "outcome": "live_output_written",
                            "source_size_bytes": 2_000,
                            "output_size_bytes": 1_200,
                        },
                        separators=(",", ":"),
                    ),
                ),
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Already optimized",
                    detail=json.dumps({"outcome": "live_skipped_not_required"}, separators=(",", ":")),
                ),
            ]
        )
        db.commit()

    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output_written_count"] == 2
    assert body["already_optimized_count"] == 1
    assert body["net_space_saved_bytes"] == 1_100
    assert body["net_space_saved_percent"] == 36.7
