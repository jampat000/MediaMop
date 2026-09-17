"""Activity history that can be filtered, exported, kept for a stated time, and removed on purpose (#469).

The removals are the part to test hardest. Both are irreversible, so each must remove exactly what
it says it will — one file's history, or all history — and never a media file or anything else.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import delete, select
from starlette.testclient import TestClient

from alembic import command
from tests.integration_helpers import auth_post, auth_put
from tests.integration_helpers import csrf as fetch_csrf
from weir.core.config import WeirSettings
from weir.core.db import create_db_engine, create_session_factory
from weir.platform.activity.classify import classify_activity
from weir.platform.activity.models import ActivityEvent
from weir.platform.activity.service import prune_activity_events, record_activity_event
from weir.refiner.refiner_file_log_model import RefinerFileLogRow

# --- what is lifted out of a detail ----------------------------------------------------------------


def test_facts_the_producer_stated_are_kept() -> None:
    facts = classify_activity(
        event_type="refiner.file_remux_pass_completed",
        detail=json.dumps({"trigger": "Scheduled", "result": "skipped", "library_id": 3, "run_id": 41}),
    )
    assert (facts.trigger, facts.result, facts.library_id, facts.run_key) == ("scheduled", "skipped", 3, "run:41")


def test_a_failed_pass_is_failed_even_when_its_event_type_says_completed() -> None:
    facts = classify_activity(
        event_type="refiner.file_remux_pass_completed",
        detail=json.dumps({"ok": False, "relative_media_path": "Film/film.mkv"}),
    )
    assert facts.result == "failed"
    assert facts.relative_path == "Film/film.mkv"


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        ("refiner.file_passed_through", "success"),
        ("refiner.file_reject_fell_back", "warning"),
        ("auth.login_failed", "failed"),
        ("refiner.file_processing_progress", "running"),
        ("auth.logout", None),
    ],
)
def test_a_result_is_read_from_the_event_type_only_when_plain(event_type: str, expected: str | None) -> None:
    assert classify_activity(event_type=event_type, detail=None).result == expected


def test_nothing_is_invented_from_a_value_outside_the_standard() -> None:
    facts = classify_activity(event_type="x.y", detail=json.dumps({"trigger": "because", "result": "great"}))
    assert facts.trigger is None
    assert facts.result is None


# --- the API -----------------------------------------------------------------------------------------


def _factory():
    return create_session_factory(create_db_engine(WeirSettings.load()))


@pytest.fixture
def seeded() -> None:
    now = datetime.now(UTC)
    with _factory()() as db:
        db.execute(delete(ActivityEvent))
        db.execute(delete(RefinerFileLogRow))
        for title, detail in (
            ("Heat was handed back", {"trigger": "scheduled", "library_id": 1, "relative_media_path": "Heat/heat.mkv"}),
            ("Heat failed", {"trigger": "retry", "ok": False, "library_id": 1, "relative_media_path": "Heat/heat.mkv"}),
            ("Alien processed", {"trigger": "manual", "library_id": 1, "relative_media_path": "Alien/alien.mkv"}),
            ("Show processed", {"trigger": "webhook", "library_id": 2, "relative_media_path": "Show/S01E01.mkv"}),
        ):
            record_activity_event(
                db,
                event_type="refiner.file_remux_pass_completed",
                module="refiner",
                title=title,
                detail=json.dumps(detail),
            )
        for path in ("Heat/heat.mkv", "Alien/alien.mkv"):
            db.add(RefinerFileLogRow(library_id=1, relative_path=path, title="pass", recorded_at=now))
        db.commit()


def _login(client: TestClient, username: str = "alice", password: str = "test-password-strong") -> TestClient:
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": username, "password": password, "csrf_token": fetch_csrf(client)},
    )
    assert r.status_code == 200, r.text
    return client


def _titles(client: TestClient, **params: object) -> list[str]:
    # Signing in records its own event; these tests are about the Refiner history they seeded.
    r = client.get("/api/v1/activity/recent", params={"module": "refiner", **params})
    assert r.status_code == 200, r.text
    return sorted(item["title"] for item in r.json()["items"])


def test_history_filters_on_why_how_where_and_which_file(client_with_admin: TestClient, seeded: None) -> None:
    client = _login(client_with_admin)
    assert _titles(client, trigger="webhook") == ["Show processed"]
    assert _titles(client, result="failed") == ["Heat failed"]
    assert _titles(client, library_id=2) == ["Show processed"]
    assert _titles(client, file="heat.mkv") == ["Heat failed", "Heat was handed back"]


def test_the_page_is_told_how_far_back_history_goes(client_with_admin: TestClient, seeded: None) -> None:
    body = _login(client_with_admin).get("/api/v1/activity/recent", params={"module": "refiner"}).json()
    assert body["retention_days"] == 90
    assert body["oldest_event_at"] is not None
    assert body["items"][0]["relative_path"]


def test_a_filtered_range_exports_as_csv_and_json(client_with_admin: TestClient, seeded: None) -> None:
    client = _login(client_with_admin)
    as_csv = client.get("/api/v1/activity/export", params={"format": "csv", "file": "heat.mkv"})
    assert as_csv.status_code == 200, as_csv.text
    assert "attachment" in as_csv.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(as_csv.text)))
    assert sorted(r["title"] for r in rows) == ["Heat failed", "Heat was handed back"]
    assert {r["trigger"] for r in rows} == {"scheduled", "retry"}

    as_json = client.get("/api/v1/activity/export", params={"format": "json", "trigger": "manual", "module": "refiner"})
    assert as_json.status_code == 200
    assert [r["title"] for r in as_json.json()] == ["Alien processed"]


def test_removing_one_files_history_says_what_goes_then_removes_only_that(
    client_with_admin: TestClient, seeded: None, tmp_path: Path
) -> None:
    client = _login(client_with_admin)
    media = tmp_path / "heat.mkv"
    media.write_bytes(b"not touched")

    preview = client.get("/api/v1/activity/file-history", params={"relative_path": "Heat/heat.mkv", "library_id": 1})
    assert preview.status_code == 200, preview.text
    assert (preview.json()["activity_events"], preview.json()["processing_records"]) == (2, 1)
    assert "does not touch the file itself" in preview.json()["message"]

    removed = auth_post(
        client,
        "/api/v1/activity/file-history/remove",
        json={"csrf_token": fetch_csrf(client), "relative_path": "Heat/heat.mkv", "library_id": 1},
    )
    assert removed.status_code == 200, removed.text
    assert (removed.json()["activity_events_deleted"], removed.json()["processing_records_deleted"]) == (2, 1)

    assert _titles(client) == ["Alien processed", "Show processed"]
    with _factory()() as db:
        assert [r.relative_path for r in db.scalars(select(RefinerFileLogRow))] == ["Alien/alien.mkv"]
    assert media.read_bytes() == b"not touched"


def test_removing_history_needs_an_operator_and_a_fresh_token(client_with_viewer: TestClient, seeded: None) -> None:
    client = _login(client_with_viewer, "bob", "viewer-password-here")
    r = auth_post(
        client,
        "/api/v1/activity/file-history/remove",
        json={"csrf_token": fetch_csrf(client), "relative_path": "Heat/heat.mkv"},
    )
    assert r.status_code == 403


def test_clearing_all_history_is_previewed_without_removing_anything(
    client_with_admin: TestClient, seeded: None
) -> None:
    client = _login(client_with_admin)
    preview = client.get("/api/v1/suite/operational-history/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "preview"
    everything = client.get("/api/v1/activity/recent").json()["total"]
    assert preview.json()["activity_events_deleted"] == everything
    assert len(_titles(client)) == 4


# --- retention ------------------------------------------------------------------------------------------


def test_activity_older_than_the_horizon_is_pruned_and_zero_keeps_everything() -> None:
    now = datetime.now(UTC)
    with _factory()() as db:
        db.execute(delete(ActivityEvent))
        db.add_all(
            [
                ActivityEvent(event_type="a.old", module="refiner", title="old", created_at=now - timedelta(days=91)),
                ActivityEvent(event_type="a.new", module="refiner", title="new", created_at=now - timedelta(days=89)),
            ]
        )
        db.commit()
        assert prune_activity_events(db, retention_days=0) == 0
        assert prune_activity_events(db, retention_days=90) == 1
        db.commit()
        assert [e.title for e in db.scalars(select(ActivityEvent))] == ["new"]


def test_the_activity_horizon_is_a_saved_setting(client_with_admin: TestClient) -> None:
    client = _login(client_with_admin)
    current = client.get("/api/v1/suite/settings").json()
    assert current["activity_retention_days"] == 90
    body = {
        "csrf_token": fetch_csrf(client),
        "product_display_name": current["product_display_name"],
        "app_timezone": current["app_timezone"],
        "log_retention_days": current["log_retention_days"],
        "activity_retention_days": 365,
    }
    saved = auth_put(client, "/api/v1/suite/settings", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["activity_retention_days"] == 365
    body.update(csrf_token=fetch_csrf(client), activity_retention_days=90)
    assert auth_put(client, "/api/v1/suite/settings", json=body).status_code == 200


def test_job_rows_now_default_to_the_same_ninety_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEIR_JOB_ROWS_RETENTION_DAYS", raising=False)
    assert WeirSettings.load().job_rows_retention_days == 90


# --- the migration backfills what was already recorded ---------------------------------------------------


def test_events_recorded_before_the_upgrade_become_filterable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WEIR_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    home = tmp_path / "weirhome_activity_facts"
    home.mkdir()
    monkeypatch.setenv("WEIR_HOME", str(home))
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(backend)
    cfg = Config(str(backend / "alembic.ini"))

    command.upgrade(cfg, "0033_refiner_library_media_type")
    engine = create_db_engine(WeirSettings.load())
    with engine.begin() as conn:
        # A greenfield 0001 builds today's models, so clear anything it pre-filled to model old rows.
        conn.execute(
            sa.text(
                "insert into activity_events (event_type, module, title, detail) values "
                "('refiner.file_passed_through', 'refiner', 'old', :detail)"
            ),
            {"detail": json.dumps({"library_id": 7, "relative_media_path": "Old/old.mkv", "trigger": "scheduled"})},
        )
        columns = {c["name"] for c in sa.inspect(conn).get_columns("activity_events")}
        if "relative_path" in columns:
            conn.execute(sa.text("update activity_events set trigger = null, result = null, relative_path = null"))
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_db_engine(WeirSettings.load())
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("select trigger, result, library_id, relative_path from activity_events where title = 'old'")
        ).one()
    assert tuple(row) == ("scheduled", "success", 7, "Old/old.mkv")
