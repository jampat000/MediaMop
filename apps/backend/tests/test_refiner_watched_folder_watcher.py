"""Filesystem events as the trigger, the periodic scan as the backstop.

The load-bearing claim of this feature is that events and scans share **one** admission
implementation. That is tested directly: an event produces the same job kind the timer
produces, and every decision about a file stays in the handler that already owned it.

The second claim is that a watcher which cannot start is a slower MediaMop rather than a
broken one. Docker bind mounts, SMB and NFS frequently deliver no events at all, so that
path is not an edge case here — it is the compatibility story (#336).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_file_state_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.media_managers.connection_model  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)
from mediamop.modules.refiner.refiner_watched_folder_watcher import (
    PendingChanges,
    _run_refiner_watched_folder_watcher,
    disabled_watch_reports,
    enqueue_scan_for_library,
    libraries_to_watch,
)
from mediamop.modules.refiner.refiner_watcher_state import (
    WatcherStatus,
    clear_watcher_state,
    watcher_reports,
    watcher_summary,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(autouse=True)
def _clean_state():
    clear_watcher_state()
    yield
    clear_watcher_state()


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'watcher.sqlite'}",
        connect_args={"check_same_thread": False, "timeout": 30.0},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False, future=True
    )


def _library(session_factory, *, watch: Path, out: Path, **overrides) -> RefinerLibraryRow:
    with session_factory() as s:
        row = RefinerLibraryRow(
            name=overrides.pop("name", "Movies"),
            media_scope=overrides.pop("media_scope", "movie"),
            enabled=overrides.pop("enabled", True),
            watched_folder=str(watch.resolve()),
            output_folder=str(out.resolve()),
            schedule_enabled=False,
            **overrides,
        )
        s.add(row)
        s.commit()
        return row


def _settings(monkeypatch: pytest.MonkeyPatch) -> MediaMopSettings:
    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHER_DEBOUNCE_SECONDS", "1")
    return MediaMopSettings.load()


def _scan_jobs(session_factory) -> list[RefinerJob]:
    with session_factory() as s:
        return [
            j
            for j in s.scalars(select(RefinerJob)).all()
            if j.job_kind == REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND
        ]


# --- debounce ---------------------------------------------------------------------


def test_a_burst_of_writes_to_one_file_produces_one_candidate() -> None:
    """A chunked write — a PVR writing a recording in pieces — is one arrival, not twenty."""

    pending = PendingChanges()
    for tick in range(20):
        pending.note(1, 100.0 + tick * 0.1)

    # Still inside the debounce window: nothing is ready.
    assert pending.drain_quiet(now_monotonic=102.0, debounce_seconds=3.0) == []
    assert pending.pending_count() == 1

    # Quiet for long enough, and the whole burst becomes exactly one library id.
    assert pending.drain_quiet(now_monotonic=105.0, debounce_seconds=3.0) == [1]
    assert pending.pending_count() == 0


def test_the_debounce_window_restarts_while_writing_continues() -> None:
    pending = PendingChanges()
    pending.note(1, 100.0)
    assert pending.drain_quiet(now_monotonic=104.0, debounce_seconds=3.0) == [1]

    pending.note(1, 110.0)
    assert pending.drain_quiet(now_monotonic=111.0, debounce_seconds=3.0) == []
    assert pending.drain_quiet(now_monotonic=114.0, debounce_seconds=3.0) == [1]


def test_separate_libraries_debounce_independently() -> None:
    pending = PendingChanges()
    pending.note(1, 100.0)
    pending.note(2, 110.0)

    assert pending.drain_quiet(now_monotonic=104.0, debounce_seconds=3.0) == [1]
    assert pending.drain_quiet(now_monotonic=114.0, debounce_seconds=3.0) == [2]


# --- one admission implementation -------------------------------------------------


def test_an_event_enqueues_the_same_job_kind_the_timer_enqueues(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The load-bearing claim. The watcher decides nothing about a file.

    It enqueues the job the periodic timer enqueues, so extension checks, exclusions,
    size limits, the hold timer and size settling all stay in the one handler that
    already owns them.
    """

    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    library = _library(session_factory, watch=watch, out=out)
    settings = _settings(monkeypatch)

    with session_factory() as s, s.begin():
        fresh = s.get(RefinerLibraryRow, library.id)
        inserted, skip = enqueue_scan_for_library(s, settings, library=fresh)

    assert inserted is True
    assert skip is None

    jobs = _scan_jobs(session_factory)
    assert len(jobs) == 1
    body = json.loads(jobs[0].payload_json or "{}")
    # The only thing distinguishing it from a timer scan is why it happened.
    assert body["scan_trigger"] == "filesystem_event"
    assert body["media_scope"] == "movie"
    assert body["library_id"] == library.id


def test_an_event_does_not_pile_a_second_scan_onto_a_queued_one(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    library = _library(session_factory, watch=watch, out=out)
    settings = _settings(monkeypatch)

    with session_factory() as s, s.begin():
        enqueue_scan_for_library(s, settings, library=s.get(RefinerLibraryRow, library.id))
    with session_factory() as s, s.begin():
        inserted, skip = enqueue_scan_for_library(s, settings, library=s.get(RefinerLibraryRow, library.id))

    assert inserted is False
    assert skip == "active_scan_already_queued"
    assert len(_scan_jobs(session_factory)) == 1


def test_a_tv_library_enqueues_a_tv_scoped_scan(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    library = _library(session_factory, watch=watch, out=out, name="TV", media_scope="tv")
    settings = _settings(monkeypatch)

    with session_factory() as s, s.begin():
        enqueue_scan_for_library(s, settings, library=s.get(RefinerLibraryRow, library.id))

    body = json.loads(_scan_jobs(session_factory)[0].payload_json or "{}")
    assert body["media_scope"] == "tv"


# --- which libraries get watched ---------------------------------------------------


def test_a_library_with_events_switched_off_is_not_watched_but_is_reported(session_factory, tmp_path: Path) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    _library(session_factory, watch=watch, out=out, file_system_events_enabled=False)

    with session_factory() as s:
        assert libraries_to_watch(s) == []
        reports = disabled_watch_reports(s)

    assert len(reports) == 1
    assert reports[0].status is WatcherStatus.DISABLED
    # Switched off deliberately is not degraded; treating it as such trains people to
    # ignore the signal.
    assert reports[0].degraded is False
    assert "scan interval" in reports[0].detail


def test_a_disabled_library_is_not_watched(session_factory, tmp_path: Path) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    _library(session_factory, watch=watch, out=out, enabled=False)

    with session_factory() as s:
        assert libraries_to_watch(s) == []


def test_a_library_with_no_watched_folder_is_not_watched(session_factory, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    with session_factory() as s:
        s.add(
            RefinerLibraryRow(
                name="Unconfigured",
                media_scope="movie",
                enabled=True,
                watched_folder="",
                output_folder=str(out.resolve()),
            )
        )
        s.commit()
        assert libraries_to_watch(s) == []


# --- the fallback ------------------------------------------------------------------


def test_an_unavailable_watcher_falls_back_to_polling_and_logs_once(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Docker bind mount / SMB share case, which is common rather than exotic.

    MediaMop must keep finding work on the scan interval, say so once, and not fail
    readiness over a slower path to the same result.
    """

    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    _library(session_factory, watch=watch, out=out)
    settings = _settings(monkeypatch)

    monkeypatch.setattr(
        "mediamop.modules.refiner.refiner_watched_folder_watcher._watchdog_modules",
        lambda: None,
    )
    # Record what the module logs by standing in for its logger. Handler- and
    # caplog-based capture both depend on how the suite configures logging; this asserts
    # the call itself, which is the property that matters — once, not once per tick.
    warnings: list[str] = []

    class _RecordingLogger:
        def warning(self, message: str, *args: object) -> None:
            warnings.append(message % args if args else message)

        def info(self, *args: object, **kwargs: object) -> None:
            pass

        def debug(self, *args: object, **kwargs: object) -> None:
            pass

        def exception(self, *args: object, **kwargs: object) -> None:
            pass

    monkeypatch.setattr("mediamop.modules.refiner.refiner_watched_folder_watcher.logger", _RecordingLogger())

    async def _drive_and_capture() -> tuple:
        stop = asyncio.Event()
        task = asyncio.create_task(
            _run_refiner_watched_folder_watcher(session_factory, stop_event=stop, settings=settings)
        )
        # Read the state before the task's own shutdown clears it.
        await asyncio.sleep(0.2)
        captured = watcher_reports()
        summary = watcher_summary()
        stop.set()
        await asyncio.wait_for(task, timeout=5)
        return captured, summary

    reports, (ok, detail) = asyncio.run(_drive_and_capture())

    assert len(reports) == 1
    assert reports[0].status is WatcherStatus.POLLING_FALLBACK
    assert reports[0].degraded is True

    # Slower, not broken: readiness still passes and the sentence says what it means.
    assert ok is True
    assert "scan interval" in detail

    assert len(warnings) == 1, "the fallback must log once, not once per tick"
    assert "scan interval" in warnings[0]


def test_a_folder_that_cannot_be_watched_reports_itself_and_does_not_raise(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "gone"
    out = tmp_path / "out"
    out.mkdir()
    _library(session_factory, watch=missing, out=out)
    settings = _settings(monkeypatch)

    async def _drive_and_capture() -> tuple:
        stop = asyncio.Event()
        task = asyncio.create_task(
            _run_refiner_watched_folder_watcher(session_factory, stop_event=stop, settings=settings)
        )
        await asyncio.sleep(0.2)
        captured = watcher_reports()
        stop.set()
        await asyncio.wait_for(task, timeout=5)
        return captured

    reports = asyncio.run(_drive_and_capture())

    assert len(reports) == 1
    assert reports[0].status is WatcherStatus.POLLING_FALLBACK
    assert "network shares" in reports[0].detail


def test_readiness_says_nothing_alarming_when_no_library_is_watched() -> None:
    ok, detail = watcher_summary()

    assert ok is True
    assert "No libraries" in detail


# --- real filesystem events --------------------------------------------------------


def _run_watcher_until_scan(session_factory, settings, *, act, timeout: float = 20.0) -> list[RefinerJob]:
    """Start the watcher, perform ``act`` on the tree, wait for a scan job to appear."""

    async def _drive() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(
            _run_refiner_watched_folder_watcher(session_factory, stop_event=stop, settings=settings)
        )
        try:
            # Let the observer schedule its watches before touching the tree.
            await asyncio.sleep(1.0)
            act()
            deadline = asyncio.get_running_loop().time() + timeout
            while asyncio.get_running_loop().time() < deadline:
                if _scan_jobs(session_factory):
                    return
                await asyncio.sleep(0.25)
        finally:
            stop.set()
            await asyncio.wait_for(task, timeout=10)

    asyncio.run(_drive())
    return _scan_jobs(session_factory)


def test_a_file_appearing_becomes_a_candidate_without_waiting_for_the_scan_interval(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    _library(session_factory, watch=watch, out=out)
    settings = _settings(monkeypatch)

    jobs = _run_watcher_until_scan(
        session_factory,
        settings,
        act=lambda: (watch / "Gate Test 2001.mkv").write_bytes(b"x" * 2048),
    )

    assert len(jobs) == 1
    assert json.loads(jobs[0].payload_json or "{}")["scan_trigger"] == "filesystem_event"


def test_a_file_moved_into_a_watched_folder_becomes_a_candidate(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The common shape: a download client writes elsewhere and moves the finished file in."""

    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    staged = staging / "Gate Test 2001.mkv"
    staged.write_bytes(b"x" * 2048)
    _library(session_factory, watch=watch, out=out)
    settings = _settings(monkeypatch)

    jobs = _run_watcher_until_scan(
        session_factory,
        settings,
        act=lambda: staged.replace(watch / "Gate Test 2001.mkv"),
    )

    assert len(jobs) == 1


def test_a_chunked_write_produces_one_scan_not_one_per_chunk(
    session_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PVR writing parts of a recording every few seconds is one arrival."""

    watch = tmp_path / "watch"
    watch.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    _library(session_factory, watch=watch, out=out)
    settings = _settings(monkeypatch)

    def _chunked() -> None:
        target = watch / "Recording.mkv"
        with target.open("wb") as handle:
            for _ in range(10):
                handle.write(b"x" * 4096)
                handle.flush()

    jobs = _run_watcher_until_scan(session_factory, settings, act=_chunked)

    assert len(jobs) == 1, "ten writes must debounce into one scan"
