"""The schedule gates work, not only enqueue — and a pause that expires on its own.

The bug this closes is specific: a window that gated enqueue let a job queued two minutes
before closing run all night, which is the exact outcome the window existed to prevent.
So the tests that matter here are about **leasing**, not about enqueueing (#337).

In-flight policy is "a running job finishes". That is asserted too, because it is a
promise the UI makes and a promise nobody should be able to change by accident.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.platform.suite_settings.model  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import claim_next_eligible_refiner_job, refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_schedule_grid import (
    SLOTS_PER_DAY,
    SLOTS_PER_WEEK,
    ScheduleGridError,
    grid_allows,
    grid_from_days_and_times,
    next_open_slot,
    normalize_grid,
    slot_index,
)
from mediamop.modules.refiner.refiner_work_admission import (
    evaluate_work_admission,
    is_detection_job_kind,
    library_window_open,
    resolve_pause_state,
)
from mediamop.platform.suite_settings.model import SuiteSettingsRow

REMUX = "refiner.file.remux_pass.v1"
SCAN = "refiner.watched_folder.remux_scan_dispatch.v1"

# A Wednesday at 14:00 UTC.
NOW = datetime(2026, 8, 26, 14, 0, tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sched.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()
    s.add(SuiteSettingsRow(id=1, app_timezone="UTC"))
    s.commit()
    return s


def _library(session: Session, **overrides) -> RefinerLibraryRow:
    row = RefinerLibraryRow(
        name=overrides.pop("name", "Movies"),
        media_scope="movie",
        enabled=overrides.pop("enabled", True),
        watched_folder="/srv/in",
        output_folder="/srv/out",
        schedule_enabled=overrides.pop("schedule_enabled", True),
        **overrides,
    )
    session.add(row)
    session.commit()
    return row


def _queue(session: Session, *, kind: str, library_id: int | None = None, key: str = "k") -> RefinerJob:
    payload: dict[str, object] = {"media_scope": "movie"}
    if library_id is not None:
        payload["library_id"] = library_id
    job = refiner_enqueue_or_get_job(
        session, dedupe_key=f"{kind}:{key}", job_kind=kind, payload_json=json.dumps(payload)
    )
    session.commit()
    return job


def _claim(session: Session, admission, *, owner: str = "w1") -> RefinerJob | None:
    job = claim_next_eligible_refiner_job(
        session,
        lease_owner=owner,
        lease_expires_at=NOW + timedelta(hours=1),
        now=NOW,
        admission=admission,
    )
    session.commit()
    return job


# --- the grid ----------------------------------------------------------------------


def test_an_empty_grid_means_no_restriction_and_an_all_zero_grid_means_never() -> None:
    # These must not be conflated: every existing library has no grid, and reading that
    # as "never" would stop all work on upgrade.
    assert grid_allows("", timezone_name="UTC", now=NOW) is True
    assert grid_allows(None, timezone_name="UTC", now=NOW) is True
    assert grid_allows("0" * SLOTS_PER_WEEK, timezone_name="UTC", now=NOW) is False


def test_a_grid_of_the_wrong_length_is_refused_rather_than_padded() -> None:
    with pytest.raises(ScheduleGridError, match="672 characters"):
        normalize_grid("101")
    with pytest.raises(ScheduleGridError, match="only contain 0 and 1"):
        normalize_grid("2" * SLOTS_PER_WEEK)


def test_a_malformed_stored_grid_allows_work_rather_than_stopping_it() -> None:
    """A display bug must not become a stoppage."""

    assert grid_allows("nonsense", timezone_name="UTC", now=NOW) is True


def test_the_grid_is_read_at_quarter_hour_resolution() -> None:
    slots = ["0"] * SLOTS_PER_WEEK
    # Wednesday is weekday 2. 14:15 only.
    slots[slot_index(weekday=2, hour=14, minute=15)] = "1"
    grid = "".join(slots)

    assert grid_allows(grid, timezone_name="UTC", now=NOW.replace(minute=14)) is False
    assert grid_allows(grid, timezone_name="UTC", now=NOW.replace(minute=15)) is True
    assert grid_allows(grid, timezone_name="UTC", now=NOW.replace(minute=29)) is True
    assert grid_allows(grid, timezone_name="UTC", now=NOW.replace(minute=30)) is False


def test_the_grid_is_evaluated_in_the_suite_timezone() -> None:
    slots = ["0"] * SLOTS_PER_WEEK
    # 14:00 UTC is 10:00 in New York on this date.
    slots[slot_index(weekday=2, hour=10, minute=0)] = "1"
    grid = "".join(slots)

    assert grid_allows(grid, timezone_name="America/New_York", now=NOW) is True
    assert grid_allows(grid, timezone_name="UTC", now=NOW) is False


def test_an_unknown_timezone_falls_back_to_utc_rather_than_raising() -> None:
    slots = ["0"] * SLOTS_PER_WEEK
    slots[slot_index(weekday=2, hour=14, minute=0)] = "1"

    assert grid_allows("".join(slots), timezone_name="Mars/Olympus", now=NOW) is True


def test_a_grid_built_from_days_and_times_reproduces_that_window() -> None:
    grid = grid_from_days_and_times(days="mon,wed", start="09:00", end="17:00")

    assert grid_allows(grid, timezone_name="UTC", now=NOW) is True  # Wednesday 14:00
    assert grid_allows(grid, timezone_name="UTC", now=NOW.replace(hour=18)) is False
    assert grid_allows(grid, timezone_name="UTC", now=NOW + timedelta(days=1)) is False  # Thursday


def test_an_overnight_window_carries_into_the_next_day() -> None:
    grid = grid_from_days_and_times(days="wed", start="22:00", end="04:00")

    assert grid_allows(grid, timezone_name="UTC", now=NOW.replace(hour=23)) is True
    # Thursday 02:00 is inside a window that started on Wednesday night.
    assert grid_allows(grid, timezone_name="UTC", now=(NOW + timedelta(days=1)).replace(hour=2)) is True
    assert grid_allows(grid, timezone_name="UTC", now=NOW.replace(hour=12)) is False


def test_days_that_cannot_be_parsed_become_no_restriction_not_a_wrong_window() -> None:
    # "Nearly right" is worse than "unrestricted" here: it would run heavy work at a time
    # the operator deliberately excluded.
    assert grid_from_days_and_times(days="", start="09:00", end="17:00") == ""
    assert grid_from_days_and_times(days="mon", start="nonsense", end="17:00") == ""


def test_a_closed_window_reports_when_it_next_opens() -> None:
    slots = ["0"] * SLOTS_PER_WEEK
    slots[slot_index(weekday=2, hour=16, minute=0)] = "1"

    opens = next_open_slot("".join(slots), timezone_name="UTC", now=NOW)

    assert opens == datetime(2026, 8, 26, 16, 0, tzinfo=UTC)


def test_a_grid_that_never_opens_reports_no_time_rather_than_a_wrong_one() -> None:
    assert next_open_slot("0" * SLOTS_PER_WEEK, timezone_name="UTC", now=NOW) is None
    assert next_open_slot("", timezone_name="UTC", now=NOW) is None


# --- the pause ---------------------------------------------------------------------


def test_a_pause_with_no_expiry_stays_paused(session: Session) -> None:
    row = session.get(SuiteSettingsRow, 1)
    row.processing_paused = True
    session.commit()

    state = resolve_pause_state(row, now=NOW)

    assert state.paused is True
    assert state.expired is False
    assert "when you resume it" in state.reason


def test_a_pause_expires_on_its_own_without_a_background_task(session: Session) -> None:
    """A pause set before a restart must still lapse on time."""

    row = session.get(SuiteSettingsRow, 1)
    row.processing_paused = True
    row.processing_paused_until = NOW - timedelta(minutes=1)
    session.commit()

    state = resolve_pause_state(row, now=NOW)

    assert state.paused is False
    assert state.expired is True


def test_a_pause_that_has_not_yet_expired_is_still_a_pause_and_says_when(session: Session) -> None:
    row = session.get(SuiteSettingsRow, 1)
    row.processing_paused = True
    row.processing_paused_until = NOW + timedelta(hours=2)
    session.commit()

    state = resolve_pause_state(row, now=NOW)

    assert state.paused is True
    assert "2026-08-26 16:00 UTC" in state.reason


def test_detection_job_kinds_are_recognised() -> None:
    assert is_detection_job_kind(SCAN) is True
    assert is_detection_job_kind(REMUX) is False


# --- leasing: the point of the issue ------------------------------------------------


def test_a_job_is_not_leased_for_a_library_outside_its_window(session: Session) -> None:
    """Queued before the window closed, and still not started after it did."""

    library = _library(session, schedule_grid="0" * SLOTS_PER_WEEK)
    _queue(session, kind=REMUX, library_id=library.id)

    admission = evaluate_work_admission(session, now=NOW)

    assert library.id in admission.blocked_library_ids
    assert _claim(session, admission) is None
    assert session.scalars(select(RefinerJob)).one().status == RefinerJobStatus.PENDING.value


def test_a_job_is_leased_once_the_window_opens(session: Session) -> None:
    slots = ["0"] * SLOTS_PER_WEEK
    for slot in range(SLOTS_PER_DAY):
        slots[2 * SLOTS_PER_DAY + slot] = "1"  # all Wednesday
    library = _library(session, schedule_grid="".join(slots))
    _queue(session, kind=REMUX, library_id=library.id)

    claimed = _claim(session, evaluate_work_admission(session, now=NOW))

    assert claimed is not None
    assert claimed.status == RefinerJobStatus.LEASED.value


def test_one_library_being_shut_does_not_block_another(session: Session) -> None:
    shut = _library(session, name="Movies", schedule_grid="0" * SLOTS_PER_WEEK)
    open_lib = _library(session, name="TV")
    _queue(session, kind=REMUX, library_id=shut.id, key="shut")
    _queue(session, kind=REMUX, library_id=open_lib.id, key="open")

    claimed = _claim(session, evaluate_work_admission(session, now=NOW))

    assert claimed is not None
    assert json.loads(claimed.payload_json or "{}")["library_id"] == open_lib.id


def test_a_job_naming_no_library_is_still_claimable(session: Session) -> None:
    """Suite-wide and pre-library jobs must not be swept up by an exclusion list."""

    shut = _library(session, schedule_grid="0" * SLOTS_PER_WEEK)
    _queue(session, kind=REMUX, library_id=shut.id, key="shut")
    _queue(session, kind=SCAN, key="nolib")

    claimed = _claim(session, evaluate_work_admission(session, now=NOW))

    assert claimed is not None
    assert claimed.job_kind == SCAN


def test_a_running_job_finishes_when_the_window_closes(session: Session) -> None:
    """The documented in-flight policy, asserted so nobody changes it by accident.

    Killing a transcode partway through wastes the work and leaves a partial file. The
    window means "start nothing new".
    """

    library = _library(session)
    _queue(session, kind=REMUX, library_id=library.id)
    leased = _claim(session, evaluate_work_admission(session, now=NOW))
    assert leased is not None

    # Now the window shuts underneath the running job.
    library.schedule_grid = "0" * SLOTS_PER_WEEK
    session.commit()

    admission = evaluate_work_admission(session, now=NOW)
    assert library.id in admission.blocked_library_ids
    # Untouched, and still owned by the worker that leased it.
    still = session.scalars(select(RefinerJob)).one()
    assert still.status == RefinerJobStatus.LEASED.value
    assert still.lease_owner == "w1"
    # And nothing new starts.
    assert _claim(session, admission, owner="w2") is None


def test_a_disabled_library_blocks_leasing_too(session: Session) -> None:
    library = _library(session, enabled=False)
    _queue(session, kind=REMUX, library_id=library.id)

    assert _claim(session, evaluate_work_admission(session, now=NOW)) is None


def test_a_library_with_scheduling_off_is_never_blocked(session: Session) -> None:
    library = _library(session, schedule_enabled=False, schedule_grid="0" * SLOTS_PER_WEEK)

    assert library_window_open(library, timezone_name="UTC", now=NOW) is True


# --- leasing under a pause ----------------------------------------------------------


def _pause(session: Session, *, scan_while_paused: bool, until: datetime | None = None) -> None:
    row = session.get(SuiteSettingsRow, 1)
    row.processing_paused = True
    row.scan_while_paused = scan_while_paused
    row.processing_paused_until = until
    session.commit()


def test_a_pause_stops_processing_but_scanning_continues_by_default(session: Session) -> None:
    """The right decomposition: keep noticing files while declining to work on them."""

    library = _library(session)
    _queue(session, kind=REMUX, library_id=library.id, key="remux")
    _queue(session, kind=SCAN, library_id=library.id, key="scan")
    _pause(session, scan_while_paused=True)

    claimed = _claim(session, evaluate_work_admission(session, now=NOW))

    assert claimed is not None
    assert claimed.job_kind == SCAN
    # And the remux stays put.
    assert _claim(session, evaluate_work_admission(session, now=NOW), owner="w2") is None


def test_scan_while_paused_off_stops_everything(session: Session) -> None:
    library = _library(session)
    _queue(session, kind=SCAN, library_id=library.id, key="scan")
    _pause(session, scan_while_paused=False)

    assert _claim(session, evaluate_work_admission(session, now=NOW)) is None


def test_work_resumes_once_the_pause_expires(session: Session) -> None:
    library = _library(session)
    _queue(session, kind=REMUX, library_id=library.id)
    _pause(session, scan_while_paused=True, until=NOW + timedelta(hours=1))

    assert _claim(session, evaluate_work_admission(session, now=NOW)) is None

    later = NOW + timedelta(hours=2)
    admission = evaluate_work_admission(session, now=later)
    assert admission.pause.paused is False
    claimed = claim_next_eligible_refiner_job(
        session,
        lease_owner="w1",
        lease_expires_at=later + timedelta(hours=1),
        now=later,
        admission=admission,
    )
    session.commit()

    assert claimed is not None
    assert claimed.job_kind == REMUX


def test_no_admission_claims_exactly_as_before(session: Session) -> None:
    """Callers with nothing to do with scheduling keep the old behaviour."""

    library = _library(session, schedule_grid="0" * SLOTS_PER_WEEK)
    _queue(session, kind=REMUX, library_id=library.id)
    _pause(session, scan_while_paused=False)

    assert _claim(session, None) is not None
