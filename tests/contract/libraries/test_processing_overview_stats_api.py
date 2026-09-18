"""Port of the retired Python backend's tests/test_processing_overview_stats_api.py."""

from __future__ import annotations

import json
from pathlib import Path

from tests.contract.libraries import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import API

PATH = f"{API}/processing/overview-stats"


def _remux_event(conn, *, title: str, detail: dict) -> None:
    seed.insert_activity_event(
        conn,
        event_type=h.REMUX_PASS_COMPLETED_EVENT,
        module="processing",
        title=title,
        detail=json.dumps(detail, separators=(",", ":")),
    )


def test_processing_overview_stats_requires_auth(client) -> None:
    r = client.get(PATH)
    assert r.status_code == 401


def test_processing_overview_stats_shape(admin) -> None:
    r = admin.get(PATH)
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


def test_processing_overview_stats_aggregates_remux_savings(server_factory, client_factory) -> None:
    sut = server_factory()
    home = Path(sut.home)
    out1 = home / "stats-out-1.mkv"
    out2 = home / "stats-out-2.mkv"
    unchanged = home / "stats-unchanged.mkv"
    for p in (out1, out2, unchanged):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"ok")
    with seed.stopped(sut) as conn:
        conn.execute("DELETE FROM activity_events")
        _remux_event(
            conn,
            title="Remux one",
            detail={
                "outcome": "live_output_written",
                "source_size_bytes": 1_000,
                "output_size_bytes": 700,
                "output_file": str(out1),
            },
        )
        _remux_event(
            conn,
            title="Remux two",
            detail={
                "outcome": "live_output_written",
                "source_size_bytes": 2_000,
                "output_size_bytes": 1_200,
                "output_file": str(out2),
            },
        )
        _remux_event(
            conn,
            title="Already optimized",
            detail={
                "outcome": "live_skipped_not_required",
                "output_copied_without_remux": True,
                "output_file": str(unchanged),
            },
        )

    admin = h.signed_in_admin(sut, client_factory)
    r = admin.get(PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output_written_count"] == 2
    assert body["already_optimized_count"] == 1
    assert body["files_processed"] == 3
    assert body["net_space_saved_bytes"] == 1_100
    assert body["net_space_saved_percent"] == 36.7


def test_processing_overview_stats_excludes_non_finalized_successes(server_factory, client_factory) -> None:
    sut = server_factory()
    home = Path(sut.home)
    finalized = home / "stats-finalized.mkv"
    finalized.parent.mkdir(parents=True, exist_ok=True)
    finalized.write_bytes(b"ok")
    missing = home / "stats-missing.mkv"
    with seed.stopped(sut) as conn:
        conn.execute("DELETE FROM activity_events")
        conn.execute("DELETE FROM jobs")
        h.insert_job(
            conn,
            dedupe_key="completed-job-without-finalized-activity",
            status="completed",
            payload={"relative_media_path": "SeenOnly.mkv"},
        )
        h.insert_job(conn, dedupe_key="failed-job", status="failed", payload={"relative_media_path": "Failed.mkv"})
        _remux_event(
            conn,
            title="Finalized",
            detail={
                "outcome": "live_output_written",
                "source_size_bytes": 100,
                "output_size_bytes": 80,
                "output_file": str(finalized),
            },
        )
        _remux_event(
            conn,
            title="Missing output",
            detail={
                "outcome": "live_output_written",
                "source_size_bytes": 100,
                "output_size_bytes": 80,
                "output_file": str(missing),
            },
        )
        _remux_event(
            conn,
            title="No-change detected only",
            detail={
                "outcome": "live_skipped_not_required",
                "output_copied_without_remux": False,
                "output_file": str(finalized),
            },
        )

    admin = h.signed_in_admin(sut, client_factory)
    r = admin.get(PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["files_processed"] == 2
    assert body["output_written_count"] == 2
    assert body["already_optimized_count"] == 0
    assert body["files_failed"] == 1
