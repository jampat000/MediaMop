"""Port of apps/backend/tests/test_suite_operational_history.py."""

from __future__ import annotations

import json

from tests.contract.support import seed
from tests.contract.support.client import API

RESET = f"{API}/suite/operational-history/reset"


def test_operational_history_reset_requires_confirmation(admin) -> None:
    r = admin.post_csrf(RESET, {"confirm": "wrong"})
    assert r.status_code == 400
    assert "RESET" in r.json()["detail"]


def test_operational_history_reset_clears_history_but_keeps_active_work(server, client_factory) -> None:
    client_factory(server).ensure_admin()
    with seed.stopped(server) as conn:
        conn.execute("DELETE FROM activity_events")
        conn.execute("DELETE FROM refiner_jobs")
        seed.insert_activity_event(
            conn,
            event_type="refiner.file_remux_pass_completed",
            module="refiner",
            title="Finished file",
            detail=json.dumps({"outcome": "live_output_written"}),
        )
        now = seed.utc_text()
        for key, status in (("refiner-done", "completed"), ("refiner-pending", "pending")):
            conn.execute(
                "INSERT INTO refiner_jobs (dedupe_key, job_kind, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (key, "refiner.file.remux_pass.v1", status, now, now),
            )

    admin = client_factory(server)
    admin.ensure_admin()
    r = admin.post_csrf(RESET, {"confirm": "RESET"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "reset"
    assert body["activity_events_deleted"] >= 1
    assert body["refiner_jobs_deleted"] == 1

    with seed.stopped(server) as conn:
        assert seed.scalar(conn, "SELECT COUNT(*) FROM activity_events") == 0
        keys = {row["dedupe_key"] for row in seed.rows(conn, "SELECT dedupe_key FROM refiner_jobs")}
    assert "refiner-done" not in keys
    assert "refiner-pending" in keys
