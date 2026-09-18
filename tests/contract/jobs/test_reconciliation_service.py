"""Contract port of the retired Python backend's tests/test_reconciliation_service.py (report and safe repairs over HTTP)."""

from __future__ import annotations

from pathlib import Path

import pytest

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

        # The CSRF token is required on .NET (#527); Python ignores the extra field.
        refused = admin.post_csrf(
            f"{REPORT}/repair",
            json={"action": issue["repair_action"], "path": issue["path"], "confirm": False},
        )
        assert refused.status_code == 400, refused.text
        assert "confirm=true" in refused.json()["detail"]
        assert artifact.exists()

        applied = admin.post_csrf(
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


TRUSTED = "http://127.0.0.1:9000"
XRW = {"X-Requested-With": "XMLHttpRequest"}
REPAIR_BODY = {"action": "remove_processing_temp_artifact", "path": "/nowhere/.x.partial", "confirm": False}


def test_reconciliation_repair_requires_a_csrf_token(admin: WeirClient) -> None:
    missing = admin.post(f"{REPORT}/repair", json=REPAIR_BODY)
    assert missing.status_code == 400, missing.text
    assert missing.json() == {"detail": "Invalid or expired CSRF token."}

    wrong = admin.post(f"{REPORT}/repair", json={**REPAIR_BODY, "csrf_token": "not-a-token"})
    assert wrong.status_code == 400, wrong.text

    # A valid token reaches the repair itself, which refuses without confirmation.
    valid = admin.post_csrf(f"{REPORT}/repair", json=REPAIR_BODY)
    assert valid.status_code == 400, valid.text
    assert "confirm=true" in valid.json()["detail"]


def test_reconciliation_repair_checks_the_browser_origin(server_factory, client_factory) -> None:
    sut = server_factory({"WEIR_TRUSTED_BROWSER_ORIGINS": TRUSTED})
    trusted = client_factory(sut, headers={"Origin": TRUSTED, **XRW})
    trusted.ensure_admin()
    token = trusted.csrf()

    evil = trusted.post(
        f"{REPORT}/repair", json={**REPAIR_BODY, "csrf_token": token}, headers={"Origin": "http://evil.test"}
    )
    assert evil.status_code == 403, evil.text
    assert evil.json() == {"detail": "Origin not allowed."}

    allowed = trusted.post(f"{REPORT}/repair", json={**REPAIR_BODY, "csrf_token": token})
    assert allowed.status_code == 400, allowed.text
    assert "confirm=true" in allowed.json()["detail"]
