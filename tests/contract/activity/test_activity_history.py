"""Contract port of the retired Python backend's tests/test_activity_history.py (filter, export, retention, removal)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.contract.activity._helpers import VIEWER_PASSWORD, VIEWER_USERNAME, insert_event, seed_history
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient
from tests.contract.support.polling import wait_until


@pytest.fixture
def seeded(server, admin, client_factory) -> WeirClient:
    """The four Processing results and two processing records; returns a fresh admin client."""

    with seed.stopped(server) as conn:
        seed_history(conn)
    client = client_factory(server)
    client.login()
    return client


def _titles(client: WeirClient, **params: object) -> list[str]:
    # Signing in records its own event; these tests are about the Processing history they seeded.
    r = client.get(f"{API}/activity/recent", params={"module": "processing", **params})
    assert r.status_code == 200, r.text
    return sorted(item["title"] for item in r.json()["items"])


def test_history_filters_on_why_how_where_and_which_file(seeded: WeirClient) -> None:
    client = seeded
    assert _titles(client, trigger="webhook") == ["Show processed"]
    assert _titles(client, result="failed") == ["Heat failed"]
    assert _titles(client, library_id=2) == ["Show processed"]
    assert _titles(client, file="heat.mkv") == ["Heat failed", "Heat was handed back"]


def test_the_page_is_told_how_far_back_history_goes(seeded: WeirClient) -> None:
    r = seeded.get(f"{API}/activity/recent", params={"module": "processing"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["retention_days"] == 90
    assert body["oldest_event_at"] is not None
    assert body["items"][0]["relative_path"]


def test_a_filtered_range_exports_as_csv_and_json(seeded: WeirClient) -> None:
    client = seeded
    as_csv = client.get(f"{API}/activity/export", params={"format": "csv", "file": "heat.mkv"})
    assert as_csv.status_code == 200, as_csv.text
    assert "attachment" in as_csv.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(as_csv.text)))
    assert sorted(r["title"] for r in rows) == ["Heat failed", "Heat was handed back"]
    assert {r["trigger"] for r in rows} == {"scheduled", "retry"}

    as_json = client.get(f"{API}/activity/export", params={"format": "json", "trigger": "manual", "module": "processing"})
    assert as_json.status_code == 200
    assert [r["title"] for r in as_json.json()] == ["Alien processed"]


def test_removing_one_files_history_says_what_goes_then_removes_only_that(
    server, seeded: WeirClient, tmp_path: Path
) -> None:
    client = seeded
    media = tmp_path / "heat.mkv"
    media.write_bytes(b"not touched")

    preview = client.get(f"{API}/activity/file-history", params={"relative_path": "Heat/heat.mkv", "library_id": 1})
    assert preview.status_code == 200, preview.text
    assert (preview.json()["activity_events"], preview.json()["processing_records"]) == (2, 1)
    assert "does not touch the file itself" in preview.json()["message"]

    removed = client.post_csrf(
        f"{API}/activity/file-history/remove", json={"relative_path": "Heat/heat.mkv", "library_id": 1}
    )
    assert removed.status_code == 200, removed.text
    assert (removed.json()["activity_events_deleted"], removed.json()["processing_records_deleted"]) == (2, 1)

    assert _titles(client) == ["Alien processed", "Show processed"]
    with seed.stopped(server) as conn:
        remaining = seed.rows(conn, "SELECT relative_path FROM file_logs ORDER BY id")
    assert [r["relative_path"] for r in remaining] == ["Alien/alien.mkv"]
    assert media.read_bytes() == b"not touched"


def test_removing_history_needs_an_operator_and_a_fresh_token(server, seeded: WeirClient, client_factory) -> None:
    client = client_factory(server)
    client.login(VIEWER_USERNAME, VIEWER_PASSWORD)
    r = client.post_csrf(f"{API}/activity/file-history/remove", json={"relative_path": "Heat/heat.mkv"})
    assert r.status_code == 403


def test_clearing_all_history_is_previewed_without_removing_anything(seeded: WeirClient) -> None:
    client = seeded
    preview = client.get(f"{API}/suite/operational-history/preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "preview"
    everything = client.get(f"{API}/activity/recent").json()["total"]
    assert preview.json()["activity_events_deleted"] == everything
    assert len(_titles(client)) == 4


def test_the_activity_horizon_is_a_saved_setting(admin: WeirClient) -> None:
    client = admin
    current = client.get(f"{API}/suite/settings").json()
    assert current["activity_retention_days"] == 90
    body = {
        "product_display_name": current["product_display_name"],
        "app_timezone": current["app_timezone"],
        "log_retention_days": current["log_retention_days"],
        "activity_retention_days": 365,
    }
    try:
        saved = client.put_csrf(f"{API}/suite/settings", json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json()["activity_retention_days"] == 365
        assert client.get(f"{API}/suite/settings").json()["activity_retention_days"] == 365
    finally:
        restored = client.put_csrf(f"{API}/suite/settings", json={**body, "activity_retention_days": 90})
        assert restored.status_code == 200, restored.text


# --- retention ------------------------------------------------------------------------------------------


def _put_activity_retention(client: WeirClient, days: int) -> None:
    current = client.get(f"{API}/suite/settings").json()
    body = {
        "product_display_name": current["product_display_name"],
        "app_timezone": current["app_timezone"],
        "log_retention_days": current["log_retention_days"],
        "activity_retention_days": days,
    }
    r = client.put_csrf(f"{API}/suite/settings", json=body)
    assert r.status_code == 200, r.text


def _insert_terminal_job(conn, *, dedupe_key: str, age: timedelta) -> None:
    stamp = seed.utc_text(datetime.now(UTC) - age)
    conn.execute(
        "INSERT INTO jobs (dedupe_key, job_kind, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (dedupe_key, "processing.work_temp_stale_sweep.v1", "completed", stamp, stamp),
    )


def _recent_processing_titles(client: WeirClient) -> list[str]:
    r = client.get(f"{API}/activity/recent", params={"module": "processing", "limit": 100})
    assert r.status_code == 200, r.text
    return sorted(item["title"] for item in r.json()["items"])


def _job_keys(client: WeirClient) -> set[str]:
    r = client.get(f"{API}/processing/jobs/inspection", params={"status": "completed", "limit": 100})
    assert r.status_code == 200, r.text
    return {job["dedupe_key"] for job in r.json()["jobs"]}


def test_activity_older_than_the_horizon_is_pruned_and_zero_keeps_everything(server_factory, client_factory) -> None:
    sut = server_factory()
    client = client_factory(sut)
    client.ensure_admin()
    _put_activity_retention(client, 0)

    now = datetime.now(UTC)
    with seed.stopped(sut) as conn:
        insert_event(conn, event_type="a.old", module="processing", title="old", created_at=now - timedelta(days=91))
        insert_event(conn, event_type="a.new", module="processing", title="new", created_at=now - timedelta(days=89))
        # A finished job past the job-row horizon: its removal shows the retention pass has run.
        _insert_terminal_job(conn, dedupe_key="marker-old-job", age=timedelta(days=200))
    client = client_factory(sut)
    client.login()
    wait_until(lambda: "marker-old-job" not in _job_keys(client), timeout_s=30, what="the retention pass to run")
    assert _recent_processing_titles(client) == ["new", "old"]

    _put_activity_retention(client, 90)
    with seed.stopped(sut) as conn:
        # Job rows now default to the same ninety days.
        _insert_terminal_job(conn, dedupe_key="job-91-days", age=timedelta(days=91))
        _insert_terminal_job(conn, dedupe_key="job-89-days", age=timedelta(days=89))
    client = client_factory(sut)
    client.login()
    wait_until(lambda: _recent_processing_titles(client) == ["new"], timeout_s=30, what="the old event to be pruned")
    keys = _job_keys(client)
    assert "job-91-days" not in keys
    assert "job-89-days" in keys
