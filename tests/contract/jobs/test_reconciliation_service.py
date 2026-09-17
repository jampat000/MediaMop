"""Contract port of apps/backend/tests/test_reconciliation_service.py (report and safe repairs over HTTP)."""

from __future__ import annotations

from pathlib import Path

from tests.contract.jobs._helpers import (
    VIEWER_PASSWORD,
    VIEWER_USERNAME,
    ensure_viewer,
    library_for_scope,
    save_library,
)
from tests.contract.support import seed
from tests.contract.support.client import API, WeirClient

REPORT = f"{API}/system/reconciliation"


def test_reconciliation_temp_artifact_repair_requires_confirmation(admin: WeirClient, tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    artifact = work / ".movie.mkv.partial"
    artifact.write_bytes(b"partial")
    movies = library_for_scope(admin, "movie")
    save_library(admin, movies["id"], watched_folder="", output_folder="", work_folder=str(work))

    try:
        report = admin.get(REPORT)
        assert report.status_code == 200, report.text
        issue = next(item for item in report.json()["issues"] if item["kind"] == "partial_temp_artifact")

        refused = admin.post(
            f"{REPORT}/repair",
            json={"action": issue["repair_action"], "path": issue["path"], "confirm": False},
        )
        assert refused.status_code == 400, refused.text
        assert "confirm=true" in refused.json()["detail"]
        assert artifact.exists()

        applied = admin.post(
            f"{REPORT}/repair",
            json={"action": issue["repair_action"], "path": issue["path"], "confirm": True},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["applied"] is True
        assert not artifact.exists()
    finally:
        save_library(admin, movies["id"], watched_folder="", output_folder="", work_folder="")


def test_reconciliation_report_rejects_viewer(server, admin: WeirClient, client_factory) -> None:
    with seed.stopped(server) as conn:
        ensure_viewer(conn)
    viewer = client_factory(server)
    viewer.login(VIEWER_USERNAME, VIEWER_PASSWORD)
    assert viewer.get(REPORT).status_code == 403


def test_reconciliation_report_allows_admin(admin: WeirClient) -> None:
    r = admin.get(REPORT)
    assert r.status_code == 200, r.text
    assert "issues" in r.json()
