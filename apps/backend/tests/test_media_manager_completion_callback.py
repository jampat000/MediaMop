"""Refiner reporting a finished hand-off back to the media manager that asked for it.

The reporting path must never raise: a manager being unreachable cannot be allowed to
fail a remux that already succeeded on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic.config import Config

from alembic import command
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.media_managers.completion_callback import (
    HandoffOrigin,
    build_completion_body,
    report_handoff_completion,
)
from mediamop.platform.media_managers.connection_service import create_connection
from tests.integration_app_runtime_quiesce import integration_test_set_home

ORIGIN = HandoffOrigin(
    source_key="deluno",
    handoff_id="handoff-1",
    callback_path="/api/integrations/processors/events",
    release_name="Blade.Runner.2049",
)


# --- the report body ---------------------------------------------------------


def test_a_written_output_is_reported_as_completed_with_its_path() -> None:
    body = build_completion_body(
        origin=ORIGIN,
        result={
            "ok": True,
            "outcome": "live_output_written",
            "output_file": "D:\\Refined\\Blade.Runner.2049\\film.mkv",
            "removed_audio": ["fre", "deu"],
            "removed_subtitles": ["spa"],
        },
    )
    assert body["status"] == "completed"
    assert body["handoffId"] == "handoff-1"
    assert body["outputPath"] == "D:\\Refined\\Blade.Runner.2049\\film.mkv"
    assert body["releaseName"] == "Blade.Runner.2049"
    assert "2 audio track(s)" in body["message"]
    assert "1 subtitle track(s)" in body["message"]


def test_a_file_that_needed_no_remux_is_still_a_completion() -> None:
    body = build_completion_body(
        origin=ORIGIN,
        result={"ok": True, "outcome": "live_skipped_not_required", "output_file": "/out/film.mkv"},
    )
    assert body["status"] == "completed"
    assert body["outputPath"] == "/out/film.mkv"
    assert "No remux was needed" in body["message"]


def test_an_operator_pass_through_is_reported_as_a_ready_unchanged_file() -> None:
    body = build_completion_body(
        origin=ORIGIN,
        result={
            "ok": True,
            "outcome": "live_skipped_not_required",
            "output_file": "/out/foreign-film.mkv",
            "pass_through_unchanged": True,
        },
    )
    assert body["status"] == "completed"
    assert body["outputPath"] == "/out/foreign-film.mkv"
    assert "passed this file through unchanged" in body["message"]


def test_a_failure_carries_the_reason_the_operator_would_see() -> None:
    body = build_completion_body(
        origin=ORIGIN,
        result={"ok": False, "outcome": "failed_before_execution", "reason": "relative_media_path is required"},
    )
    assert body["status"] == "failed"
    assert body["message"] == "relative_media_path is required"
    assert "outputPath" not in body


def test_a_guardrail_skip_is_not_reported_as_a_completion() -> None:
    """`ok` alone is not enough — a guardrail skip produced no output to import."""
    body = build_completion_body(
        origin=ORIGIN,
        result={"ok": True, "outcome": "skipped_guardrail", "source_folder_skip_reason": "File is too small."},
    )
    assert body["status"] == "failed"
    assert body["message"] == "File is too small."


# --- parsing the origin off the job payload ----------------------------------


def test_origin_is_none_when_the_job_did_not_come_from_a_manager() -> None:
    assert HandoffOrigin.from_payload({"relative_media_path": "a/b.mkv"}) is None
    assert HandoffOrigin.from_payload(None) is None
    assert HandoffOrigin.from_payload({"origin": {}}) is None


def test_origin_is_read_from_the_job_payload() -> None:
    origin = HandoffOrigin.from_payload(
        {"origin": {"source_key": "deluno", "handoff_id": "h1", "callback_path": "/cb", "release_name": "R"}}
    )
    assert origin is not None
    assert (origin.source_key, origin.handoff_id, origin.callback_path) == ("deluno", "h1", "/cb")


# --- the post itself ---------------------------------------------------------


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_callback")
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings)), settings


HANDOFF_PAYLOAD = (
    '{"relative_media_path":"a/b.mkv","media_scope":"movie",'
    '"origin":{"source_key":"deluno","handoff_id":"h1","callback_path":"/api/integrations/processors/events"}}'
)
RESULT_OK: dict[str, Any] = {"ok": True, "outcome": "live_output_written", "output_file": "/out/b.mkv"}


def test_a_job_with_no_origin_is_skipped(session_factory) -> None:
    factory, settings = session_factory
    with factory() as db:
        status = report_handoff_completion(
            db, settings, payload_json='{"relative_media_path":"a.mkv"}', result=RESULT_OK
        )
    assert status == "skipped: not a hand-off"


def test_a_handoff_with_no_configured_connection_is_skipped(session_factory) -> None:
    factory, settings = session_factory
    with factory() as db:
        status = report_handoff_completion(db, settings, payload_json=HANDOFF_PAYLOAD, result=RESULT_OK)
    assert "no enabled deluno connection" in status


def test_a_connection_without_an_address_is_skipped(session_factory) -> None:
    factory, settings = session_factory
    with factory() as db:
        create_connection(db, settings, kind="deluno", name="Deluno", base_url="")
        db.commit()
        status = report_handoff_completion(db, settings, payload_json=HANDOFF_PAYLOAD, result=RESULT_OK)
    assert "no address saved" in status


def test_the_outcome_is_posted_to_the_configured_manager(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, settings = session_factory
    captured: dict[str, Any] = {}

    def _fake_post(url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _fake_post)

    with factory() as db:
        create_connection(db, settings, kind="deluno", name="Deluno", base_url="http://10.1.1.9:5099", api_key="k1")
        db.commit()
        status = report_handoff_completion(db, settings, payload_json=HANDOFF_PAYLOAD, result=RESULT_OK)

    assert status == "reported completed to Deluno"
    assert captured["url"] == "http://10.1.1.9:5099/api/integrations/processors/events"
    assert captured["json"]["handoffId"] == "h1"
    assert captured["json"]["outputPath"] == "/out/b.mkv"
    assert captured["headers"]["X-Api-Key"] == "k1"


def test_an_unreachable_manager_does_not_raise(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, settings = session_factory

    def _boom(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", _boom)

    with factory() as db:
        create_connection(db, settings, kind="deluno", name="Deluno", base_url="http://10.1.1.9:5099")
        db.commit()
        status = report_handoff_completion(db, settings, payload_json=HANDOFF_PAYLOAD, result=RESULT_OK)

    assert status.startswith("failed: could not reach Deluno")


def test_a_rejecting_manager_is_reported_not_raised(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, settings = session_factory

    def _reject(url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(409, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _reject)

    with factory() as db:
        create_connection(db, settings, kind="deluno", name="Deluno", base_url="http://10.1.1.9:5099")
        db.commit()
        status = report_handoff_completion(db, settings, payload_json=HANDOFF_PAYLOAD, result=RESULT_OK)

    assert status == "failed: Deluno answered HTTP 409"
