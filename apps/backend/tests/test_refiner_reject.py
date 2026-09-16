"""The opt-in reject policy (#465, #471).

Rejecting removes someone's download, so most of these tests pin the refusals: every way the
reject can fall short must end in the original being handed back, never in a delete nobody was
told about, and never in a season pack losing its other episodes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner import refiner_reject
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryManagerLinkRow
from mediamop.modules.refiner.refiner_pass_through import (
    REFINER_FILE_PASS_THROUGH_JOB_KIND,
    REFINER_FILE_REJECT_JOB_KIND,
    apply_failure_policy,
    normalize_failure_policy,
)
from mediamop.modules.refiner.refiner_reject import (
    REJECT_CAPABILITY,
    make_refiner_file_reject_handler,
    reject_support,
)
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow
from mediamop.platform.media_managers.connection_service import create_connection
from mediamop.platform.media_managers.manager_dialects import _manifest_capabilities
from mediamop.platform.media_managers.manager_http import MediaManagerHttpError
from mediamop.platform.media_managers.manager_port import (
    ManagerCapabilities,
    ManagerConnection,
    ManagerDescription,
    ManagerQueueRow,
    ManagerQueueSignal,
)
from tests.refiner_library_fixtures import seed_refiner_library

_BYTES = b"\x1a\x45\xdf\xa3" + bytes(range(256)) * 8
_CAPS = ManagerCapabilities(scopes=frozenset({"movie"}), reports_queue=True, reports_library_truth=False, summary="")


# --- the policy value ----------------------------------------------------------------------------


def test_reject_is_a_recognised_policy() -> None:
    assert normalize_failure_policy("reject") == "reject"
    assert normalize_failure_policy(" REJECT ") == "reject"


def test_a_manifest_capability_list_is_read_case_insensitively() -> None:
    assert _manifest_capabilities({"capabilities": ["movies", "Processor-Reject-Regrab"]}) == frozenset(
        {"movies", REJECT_CAPABILITY}
    )
    assert _manifest_capabilities({"capabilities": "nope"}) == frozenset()
    assert _manifest_capabilities([]) == frozenset()


# --- whether reject can be offered -----------------------------------------------------------------


def _conn(kind: str, name: str = "Mgr") -> ManagerConnection:
    return ManagerConnection(kind=kind, name=name, base_url="http://10.0.0.5:1", api_key="k", connection_id=1)


class _Deletes:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail = fail


class _Port:
    def __init__(
        self,
        *,
        capabilities: frozenset[str] = frozenset(),
        status: str = "reported",
        queue: dict[str, list[dict[str, Any]]] | None = None,
        queue_status: str = "reported",
        removes: bool = False,
        deletes: _Deletes | None = None,
    ) -> None:
        self._removes = removes
        self._deletes = deletes
        self._capabilities = capabilities
        self._status = status
        self._queue = queue or {}
        self._queue_status = queue_status

    def capabilities(self) -> ManagerCapabilities:
        return ManagerCapabilities(
            scopes=frozenset({"movie"}),
            reports_queue=True,
            reports_library_truth=False,
            summary="",
            removes_queue_items=self._removes,
        )

    def remove_queue_item(self, connection: ManagerConnection, row: Any) -> None:
        assert self._deletes is not None
        self._deletes.calls.append((connection.base_url, row.get("id")))
        if self._deletes.fail:
            raise MediaManagerHttpError("HTTP 404: not found")

    def describe(self, connection: ManagerConnection) -> ManagerDescription:
        return ManagerDescription(
            connection=connection,
            status=self._status,  # type: ignore[arg-type]
            capabilities=_CAPS,
            advertised_capabilities=self._capabilities,
            detail=None if self._status == "reported" else "Could not reach it.",
        )

    def queue_rows(self, connection: ManagerConnection) -> ManagerQueueSignal:
        if self._queue_status != "reported":
            return ManagerQueueSignal(connection=connection, status="unreachable", detail="Queue unreachable.")
        rows = tuple(ManagerQueueRow(scope="movie", payload=r) for r in self._queue.get(connection.kind, []))
        return ManagerQueueSignal(connection=connection, status="reported", rows=rows)


def test_reject_needs_a_linked_manager() -> None:
    support = reject_support([])
    assert support.available is False
    assert "Link a media manager" in support.reason


def test_sonarr_and_radarr_can_always_be_asked() -> None:
    """Uses the real ports: the queue dialects declare that they remove queue items."""
    assert reject_support([_conn("radarr", "Radarr")]).available is True
    assert reject_support([_conn("sonarr", "Sonarr")]).available is True


def test_deluno_is_offered_reject_only_once_it_advertises_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refiner_reject, "port_for_kind", lambda kind: _Port())
    without = reject_support([_conn("deluno", "Deluno")])
    assert without.available is False
    assert "nothing coming to replace it" in without.reason

    monkeypatch.setattr(
        refiner_reject, "port_for_kind", lambda kind: _Port(capabilities=frozenset({REJECT_CAPABILITY}))
    )
    assert reject_support([_conn("deluno", "Deluno")]).available is True


def test_an_unreachable_deluno_is_not_offered_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refiner_reject, "port_for_kind", lambda kind: _Port(status="unreachable"))
    support = reject_support([_conn("deluno", "Deluno")])
    assert support.available is False
    assert "Could not reach it." in support.reason


# --- the job, end to end ---------------------------------------------------------------------------


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    monkeypatch.setattr(refiner_reject, "MIN_SECONDS_BETWEEN_REJECTS", 0.0)
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))

    def _clean() -> None:
        with fac() as session:
            session.execute(delete(RefinerJob))
            session.execute(delete(RefinerFileRow))
            session.execute(delete(RefinerLibraryManagerLinkRow))
            session.execute(delete(MediaManagerConnectionRow))
            session.commit()

    _clean()
    yield fac
    _clean()


@dataclass
class _Ctx:
    id: int
    payload_json: str


@dataclass
class _World:
    factory: sessionmaker[Session]
    settings: MediaMopSettings
    library_id: int
    watched: Path
    source: Path
    relative: str


def _world(factory: sessionmaker[Session], tmp_path: Path, *, kinds: tuple[str, ...], relative: str) -> _World:
    settings = MediaMopSettings.load()
    watched = tmp_path / "completed"
    output = tmp_path / "refined"
    source = watched / relative
    source.parent.mkdir(parents=True)
    output.mkdir()
    source.write_bytes(_BYTES)
    with factory() as session:
        library = seed_refiner_library(
            session, watched_folder=str(watched), output_folder=str(output), failure_policy="reject"
        )
        for kind in kinds:
            row = create_connection(
                session, settings, kind=kind, name=kind.capitalize(), base_url="http://10.0.0.5:8989", api_key="k"
            )
            session.flush()
            session.add(RefinerLibraryManagerLinkRow(library_id=library.id, connection_id=row.id))
        session.add(
            RefinerFileRow(
                library_id=library.id,
                relative_path=relative,
                status=RefinerFileStatus.PROCESSING_FAILED.value,
                status_reason="ffmpeg could not read the audio track.",
            )
        )
        session.commit()
        return _World(factory, settings, int(library.id), watched, source, relative)


def _run(world: _World, *, origin: dict[str, Any] | None = None) -> None:
    body: dict[str, Any] = {
        "relative_media_path": world.relative,
        "library_id": world.library_id,
        "reason": "ffmpeg could not read the audio track.",
        "failure_class": "execution",
    }
    if origin:
        body["origin"] = origin
    handler = make_refiner_file_reject_handler(world.settings, world.factory)
    handler(_Ctx(id=41, payload_json=json.dumps(body)))


def _file(world: _World) -> RefinerFileRow:
    with world.factory() as session:
        return session.scalars(select(RefinerFileRow).where(RefinerFileRow.relative_path == world.relative)).one()


def _jobs(world: _World, kind: str) -> list[RefinerJob]:
    with world.factory() as session:
        return list(session.scalars(select(RefinerJob).where(RefinerJob.job_kind == kind)))


def _events(world: _World, event_type: str) -> list[ActivityEvent]:
    with world.factory() as session:
        return list(session.scalars(select(ActivityEvent).where(ActivityEvent.event_type == event_type)))


def _assert_fell_back(world: _World, expected: str) -> None:
    assert world.source.read_bytes() == _BYTES
    row = _file(world)
    assert row.status != RefinerFileStatus.REJECTED.value
    assert expected in row.status_reason
    assert "ffmpeg could not read the audio track." in row.status_reason
    assert len(_jobs(world, REFINER_FILE_PASS_THROUGH_JOB_KIND)) == 1
    assert _events(world, activity_constants.REFINER_FILE_REJECT_FELL_BACK)


def test_a_final_failure_under_reject_queues_a_reject_not_a_pass_through(
    factory: sessionmaker[Session], tmp_path: Path
) -> None:
    world = _world(factory, tmp_path, kinds=(), relative="Film/film.mkv")
    origin = {"source_key": "deluno", "handoff_id": "h1", "library_id": "lib", "callback_path": "/cb"}
    with factory() as session:
        library = seed_refiner_library(session, watched_folder=str(world.watched), failure_policy="reject")
        assert (
            apply_failure_policy(
                session, library=library, relative_path=world.relative, will_retry=False, origin=origin
            )
            == "reject"
        )
        session.commit()
    (job,) = _jobs(world, REFINER_FILE_REJECT_JOB_KIND)
    payload = json.loads(job.payload_json or "{}")
    assert payload["origin"] == origin
    assert payload["reason"] == "ffmpeg could not read the audio track."
    assert _jobs(world, REFINER_FILE_PASS_THROUGH_JOB_KIND) == []


# --- through a hand-off (Deluno) --------------------------------------------------------------------

_ORIGIN = {
    "source_key": "deluno",
    "handoff_id": "h1",
    "library_id": "lib-movies",
    "callback_path": "/api/integrations/processors/events",
}


def _capture_posts(monkeypatch: pytest.MonkeyPatch, status_code: int) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []

    def _post(url: str, **kwargs: Any) -> httpx.Response:
        posts.append(kwargs["json"])
        return httpx.Response(status_code, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", _post)
    return posts


def test_an_accepted_rejection_removes_the_download(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("deluno",), relative="Film/film.mkv")
    monkeypatch.setattr(
        refiner_reject, "port_for_kind", lambda kind: _Port(capabilities=frozenset({REJECT_CAPABILITY}))
    )
    posts = _capture_posts(monkeypatch, 202)

    _run(world, origin=_ORIGIN)

    (body,) = posts
    assert body["status"] == "failed"
    assert body["disposition"] == "rejected"
    assert body["sourceRemoved"] is True
    assert body["libraryId"] == "lib-movies"
    assert body["failureClass"] == "execution"
    assert not world.source.exists()
    assert _file(world).status == RefinerFileStatus.REJECTED.value
    assert _events(world, activity_constants.REFINER_FILE_REJECTED)
    assert _events(world, activity_constants.REFINER_HANDOFF_REPORTED)
    assert _jobs(world, REFINER_FILE_PASS_THROUGH_JOB_KIND) == []


def test_a_refused_rejection_keeps_the_download_and_hands_it_back(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("deluno",), relative="Film/film.mkv")
    monkeypatch.setattr(
        refiner_reject, "port_for_kind", lambda kind: _Port(capabilities=frozenset({REJECT_CAPABILITY}))
    )
    _capture_posts(monkeypatch, 409)

    _run(world, origin=_ORIGIN)

    _assert_fell_back(world, "did not accept the rejection")
    reported = _events(world, activity_constants.REFINER_HANDOFF_REPORTED)
    assert reported and "could not tell" in reported[-1].title


def test_an_unreachable_manager_is_not_an_acceptance(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("deluno",), relative="Film/film.mkv")
    monkeypatch.setattr(
        refiner_reject, "port_for_kind", lambda kind: _Port(capabilities=frozenset({REJECT_CAPABILITY}))
    )

    def _boom(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(httpx, "post", _boom)
    _run(world, origin=_ORIGIN)
    _assert_fell_back(world, "did not accept the rejection")


def test_a_manager_that_cannot_replace_the_release_is_never_told_to_reject(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("deluno",), relative="Film/film.mkv")
    monkeypatch.setattr(refiner_reject, "port_for_kind", lambda kind: _Port())
    posts = _capture_posts(monkeypatch, 202)

    _run(world, origin=_ORIGIN)

    assert posts == []
    _assert_fell_back(world, "does not yet say it can replace a rejected release")


# --- through Sonarr / Radarr's queue ---------------------------------------------------------------


def _arr(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]], *, fail: bool = False) -> _Deletes:
    deletes = _Deletes(fail=fail)
    monkeypatch.setattr(
        refiner_reject,
        "port_for_kind",
        lambda kind: _Port(queue={"radarr": rows}, removes=kind == "radarr", deletes=deletes),
    )
    return deletes


def test_a_single_file_download_is_removed_and_blocklisted_through_the_queue(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="film.mkv")
    deletes = _arr(monkeypatch, [{"id": 17, "downloadId": "abc", "outputPath": str(world.source)}])

    _run(world)

    assert deletes.calls == [("http://10.0.0.5:8989", 17)]
    # The download client removes the data; MediaMop deletes nothing itself on this route.
    assert world.source.exists()
    assert _file(world).status == RefinerFileStatus.REJECTED.value
    assert _jobs(world, REFINER_FILE_PASS_THROUGH_JOB_KIND) == []


def test_a_download_folder_holding_only_this_video_is_rejected(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="Film.2020/film.mkv")
    (world.source.parent / "film.nfo").write_text("info")
    deletes = _arr(monkeypatch, [{"id": 5, "downloadId": "abc", "outputPath": str(world.source.parent)}])

    _run(world)

    assert [call[1] for call in deletes.calls] == [5]
    assert _file(world).status == RefinerFileStatus.REJECTED.value


def test_a_folder_with_other_videos_is_never_rejected(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="Show.S01/Show.S01E01.mkv")
    (world.source.parent / "Show.S01E02.mkv").write_bytes(_BYTES)
    deletes = _arr(monkeypatch, [{"id": 5, "downloadId": "pack", "outputPath": str(world.source.parent)}])

    _run(world)

    assert deletes.calls == []
    _assert_fell_back(world, "holds more than this one video file")


def test_a_season_pack_tracked_as_several_items_is_never_rejected(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="Show.S01E01.mkv")
    deletes = _arr(
        monkeypatch,
        [
            {"id": 1, "downloadId": "pack", "outputPath": str(world.source)},
            {"id": 2, "downloadId": "pack", "outputPath": str(world.watched / "Show.S01E02.mkv")},
        ],
    )

    _run(world)

    assert deletes.calls == []
    _assert_fell_back(world, "tracks as 2 items")


def test_two_matching_queue_items_are_never_guessed_between(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="film.mkv")
    deletes = _arr(
        monkeypatch,
        [
            {"id": 1, "downloadId": "a", "outputPath": str(world.source)},
            {"id": 2, "downloadId": "b", "outputPath": str(world.watched)},
        ],
    )

    _run(world)

    assert deletes.calls == []
    _assert_fell_back(world, "More than one download")


def test_no_matching_queue_item_hands_the_original_back(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="film.mkv")
    deletes = _arr(monkeypatch, [{"id": 1, "downloadId": "a", "outputPath": "/elsewhere/other.mkv"}])

    _run(world)

    assert deletes.calls == []
    _assert_fell_back(world, "No download in the linked media manager's queue")


def test_an_unreadable_queue_hands_the_original_back(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="film.mkv")
    deletes = _Deletes()
    monkeypatch.setattr(
        refiner_reject,
        "port_for_kind",
        lambda kind: _Port(queue_status="unreachable", removes=kind == "radarr", deletes=deletes),
    )

    _run(world)

    assert deletes.calls == []
    _assert_fell_back(world, "Queue unreachable.")


def test_a_refused_queue_delete_hands_the_original_back(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=("radarr",), relative="film.mkv")
    _arr(monkeypatch, [{"id": 17, "downloadId": "abc", "outputPath": str(world.source)}], fail=True)

    _run(world)

    _assert_fell_back(world, "did not accept the rejection")


def test_no_manager_that_can_reject_hands_the_original_back(
    factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(factory, tmp_path, kinds=(), relative="film.mkv")
    _run(world)
    _assert_fell_back(world, "No linked media manager can take a rejection")
