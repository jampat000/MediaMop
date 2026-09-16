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
from mediamop.platform.media_managers import completion_callback
from mediamop.platform.media_managers.completion_callback import (
    HandoffOrigin,
    build_completion_body,
    report_handoff_completion,
    translate_output_path,
)
from mediamop.platform.media_managers.connection_service import create_connection
from mediamop.platform.media_managers.manager_port import (
    ManagerCapabilities,
    ManagerConnection,
    ManagerDescription,
    ManagerLibraryDescriptor,
)
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


# --- what Deluno needs to accept a report (verified against its source, 2026-09-16) ---

DELUNO_ORIGIN = HandoffOrigin(
    source_key="deluno",
    handoff_id="handoff-1",
    callback_path="/api/integrations/processors/events",
    release_name=None,
    library_id="lib-movies",
)


def test_the_report_names_the_managers_library() -> None:
    body = build_completion_body(origin=DELUNO_ORIGIN, result={"ok": True, "outcome": "live_output_written"})
    assert body["libraryId"] == "lib-movies"


def test_origin_carries_the_library_id() -> None:
    origin = HandoffOrigin.from_payload({"origin": {"source_key": "deluno", "library_id": "lib-movies"}})
    assert origin is not None
    assert origin.library_id == "lib-movies"


def test_a_final_failure_says_the_original_is_held_in_place() -> None:
    body = build_completion_body(
        origin=DELUNO_ORIGIN,
        result={"ok": False, "outcome": "failed_execution", "reason": "ffmpeg failed", "failure_class": "execution"},
    )
    assert body["status"] == "failed"
    assert body["disposition"] == "held"
    assert body["sourceRemoved"] is False
    assert body["failureClass"] == "execution"


def test_a_completion_carries_no_disposition() -> None:
    body = build_completion_body(origin=DELUNO_ORIGIN, result={"ok": True, "outcome": "live_output_written"})
    assert "disposition" not in body
    assert "sourceRemoved" not in body


def test_a_pass_through_after_failure_says_the_original_was_handed_back() -> None:
    body = build_completion_body(
        origin=DELUNO_ORIGIN,
        result={
            "ok": True,
            "outcome": "live_output_written",
            "output_file": "/out/film.mkv",
            "passed_through_after_failure": True,
        },
    )
    assert body["status"] == "completed"
    assert body["message"].startswith("MediaMop could not process this file, so it handed the original back")


def test_a_translated_output_path_replaces_the_local_one() -> None:
    body = build_completion_body(
        origin=DELUNO_ORIGIN,
        result={"ok": True, "outcome": "live_output_written", "output_file": "/local/out/film.mkv"},
        output_path="/data/refined/film.mkv",
    )
    assert body["outputPath"] == "/data/refined/film.mkv"


# --- rebuilding the output path in the manager's coordinates -----------------


def test_output_path_is_rebuilt_under_a_posix_manager_folder(tmp_path: Path) -> None:
    local = tmp_path / "Refined"
    translated = translate_output_path(
        output_file=str(local / "Blade.Runner.2049" / "film.mkv"),
        local_output_folder=str(local),
        manager_output_folder="/data/refined",
    )
    assert translated == "/data/refined/Blade.Runner.2049/film.mkv"


def test_output_path_is_rebuilt_under_a_windows_manager_folder(tmp_path: Path) -> None:
    local = tmp_path / "Refined"
    translated = translate_output_path(
        output_file=str(local / "Show" / "S01E01.mkv"),
        local_output_folder=str(local),
        manager_output_folder=r"E:\Deluno\Refined",
    )
    assert translated == r"E:\Deluno\Refined\Show\S01E01.mkv"


def test_output_outside_the_local_folder_is_not_translated(tmp_path: Path) -> None:
    assert (
        translate_output_path(
            output_file=str(tmp_path / "elsewhere" / "film.mkv"),
            local_output_folder=str(tmp_path / "Refined"),
            manager_output_folder="/data/refined",
        )
        is None
    )


# --- which failures are reported, and where a completion says the file is ----


DELUNO_PAYLOAD = (
    '{"relative_media_path":"Film/film.mkv","media_scope":"movie",'
    '"origin":{"source_key":"deluno","handoff_id":"h1","library_id":"lib-movies",'
    '"callback_path":"/api/integrations/processors/events"}}'
)


def _capture_posts(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []

    def _fake_post(url: str, **kwargs: Any) -> httpx.Response:
        posts.append(kwargs["json"])
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _fake_post)
    return posts


def _deluno_connection(db, settings) -> None:
    create_connection(db, settings, kind="deluno", name="Deluno", base_url="http://10.1.1.9:5099", api_key="k1")
    db.commit()


@pytest.mark.parametrize(
    ("flag", "expected"),
    [("retry_scheduled", "will be retried"), ("pass_through_queued", "being handed back")],
)
def test_a_failure_that_is_not_final_is_not_reported(
    session_factory, monkeypatch: pytest.MonkeyPatch, flag: str, expected: str
) -> None:
    """Deluno stops importing for a hand-off once it is marked failed, which would strand the retry."""
    factory, settings = session_factory
    posts = _capture_posts(monkeypatch)
    with factory() as db:
        _deluno_connection(db, settings)
        status = report_handoff_completion(
            db,
            settings,
            payload_json=DELUNO_PAYLOAD,
            result={"ok": False, "outcome": "failed_execution", "reason": "ffmpeg failed", flag: True},
        )
    assert status.startswith("skipped:")
    assert expected in status
    assert posts == []


def test_a_final_failure_is_reported_as_held(session_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, settings = session_factory
    posts = _capture_posts(monkeypatch)
    with factory() as db:
        _deluno_connection(db, settings)
        status = report_handoff_completion(
            db,
            settings,
            payload_json=DELUNO_PAYLOAD,
            result={
                "ok": False,
                "outcome": "failed_execution",
                "reason": "ffmpeg failed",
                "retry_scheduled": False,
                "pass_through_queued": False,
                "failure_class": "execution",
            },
        )
    assert status == "reported failed to Deluno"
    assert posts[0]["libraryId"] == "lib-movies"
    assert posts[0]["disposition"] == "held"


class _StubPort:
    kind = "deluno"

    def __init__(self, libraries: tuple[ManagerLibraryDescriptor, ...]) -> None:
        self.libraries = libraries
        self.seen: list[ManagerConnection] = []

    def describe(self, connection: ManagerConnection) -> ManagerDescription:
        self.seen.append(connection)
        return ManagerDescription(
            connection=connection,
            status="reported",
            capabilities=ManagerCapabilities(
                scopes=frozenset({"movie"}), reports_queue=True, reports_library_truth=False, summary=""
            ),
            libraries=self.libraries,
        )


def _ok_result(tmp_path: Path) -> dict[str, Any]:
    local = tmp_path / "Refined"
    return {
        "ok": True,
        "outcome": "live_output_written",
        "output_file": str(local / "Film" / "film.mkv"),
        "refiner_output_folder_resolved": str(local),
    }


def _library(key: str, output_path: str | None, *, processes_before_import: bool = True) -> ManagerLibraryDescriptor:
    return ManagerLibraryDescriptor(
        key=key,
        name=key,
        media_scope="movie",
        output_path=output_path,
        processes_before_import=processes_before_import,
    )


def test_a_completion_is_reported_in_the_managers_own_path(
    session_factory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    factory, settings = session_factory
    posts = _capture_posts(monkeypatch)
    port = _StubPort((_library("lib-tv", "/data/tv-refined"), _library("lib-movies", "/data/refined")))
    monkeypatch.setattr(completion_callback, "port_for_kind", lambda kind: port)
    with factory() as db:
        _deluno_connection(db, settings)
        status = report_handoff_completion(db, settings, payload_json=DELUNO_PAYLOAD, result=_ok_result(tmp_path))
    assert status == "reported completed to Deluno"
    assert posts[0]["outputPath"] == "/data/refined/Film/film.mkv"
    assert port.seen[0].api_key == "k1"


@pytest.mark.parametrize(
    "library",
    [
        _library("lib-movies", None),
        _library("lib-movies", "/data/refined", processes_before_import=False),
        _library("lib-unrelated", "/data/refined"),
    ],
    ids=["no-output-folder", "standard-import", "different-library"],
)
def test_without_a_matching_manager_folder_the_local_path_is_reported(
    session_factory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, library: ManagerLibraryDescriptor
) -> None:
    factory, settings = session_factory
    posts = _capture_posts(monkeypatch)
    monkeypatch.setattr(completion_callback, "port_for_kind", lambda kind: _StubPort((library,)))
    result = _ok_result(tmp_path)
    with factory() as db:
        _deluno_connection(db, settings)
        report_handoff_completion(db, settings, payload_json=DELUNO_PAYLOAD, result=result)
    assert posts[0]["outputPath"] == result["output_file"]


def test_a_manager_whose_libraries_cannot_be_read_still_gets_the_report(
    session_factory, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    factory, settings = session_factory
    posts = _capture_posts(monkeypatch)

    class _Broken(_StubPort):
        def describe(self, connection: ManagerConnection) -> ManagerDescription:
            raise RuntimeError("manifest exploded")

    monkeypatch.setattr(completion_callback, "port_for_kind", lambda kind: _Broken(()))
    result = _ok_result(tmp_path)
    with factory() as db:
        _deluno_connection(db, settings)
        status = report_handoff_completion(db, settings, payload_json=DELUNO_PAYLOAD, result=result)
    assert status == "reported completed to Deluno"
    assert posts[0]["outputPath"] == result["output_file"]


def test_a_file_the_library_deleted_on_rejection_is_not_called_held() -> None:
    body = build_completion_body(
        origin=DELUNO_ORIGIN,
        result={
            "ok": False,
            "outcome": "skipped_rejected",
            "rejection_kind": "language",
            "reason": "No wanted audio language.",
            "rejected_cleanup_status": "deleted",
        },
    )
    assert body["status"] == "failed"
    assert body["sourceRemoved"] is True
    assert "disposition" not in body
