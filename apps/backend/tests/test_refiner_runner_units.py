"""A weighted budget instead of counting files.

``max_concurrent_files`` treated a 700 MB SD rip and a 60 GB 4K remux as the same unit of
work. The tests that matter here are the ones that show weighting doing something a count
cannot: a free file admitted while the budget is full, and an expensive one held back
while cheap ones run (#338).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.modules.refiner.refiner_file_state_model  # noqa: F401
import mediamop.modules.refiner.refiner_library_model  # noqa: F401
import mediamop.modules.refiner.refiner_operator_settings_model  # noqa: F401
import mediamop.platform.suite_settings.model  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import (
    claim_next_eligible_refiner_job,
    move_refiner_job_to_top,
    refiner_enqueue_or_get_job,
)
from mediamop.modules.refiner.refiner_job_queue_lookup import pending_remux_job_for_relative_path
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.modules.refiner.refiner_runner_units import (
    RunnerBudget,
    budget_from_settings,
    capacity_from_legacy_concurrency,
    resolution_class_for_dimensions,
    resolution_class_for_height,
    video_height_from_streams,
)
from mediamop.modules.refiner.refiner_work_admission import evaluate_work_admission
from mediamop.platform.suite_settings.model import SuiteSettingsRow

REMUX = "refiner.file.remux_pass.v1"
NOW = datetime(2026, 8, 26, 14, 0, tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'runner.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)()
    s.add(SuiteSettingsRow(id=1, app_timezone="UTC"))
    s.add(
        RefinerOperatorSettingsRow(
            id=1,
            max_concurrent_files=1,
            runner_capacity=2,
            runner_cost_sd=0,
            runner_cost_720p=0,
            runner_cost_1080p=1,
            runner_cost_4k=1,
            runner_cost_undetermined=0,
        )
    )
    s.commit()
    return s


def _library(session: Session, **overrides) -> RefinerLibraryRow:
    row = RefinerLibraryRow(
        name=overrides.pop("name", "Movies"),
        media_scope="movie",
        enabled=True,
        watched_folder="/srv/in",
        output_folder="/srv/out",
        schedule_enabled=False,
        **overrides,
    )
    session.add(row)
    session.commit()
    return row


def _queue(
    session: Session,
    *,
    key: str,
    cost: int,
    library_id: int | None = None,
    priority: int = 0,
    relative_path: str = "Film/film.mkv",
) -> RefinerJob:
    payload: dict[str, object] = {"media_scope": "movie", "relative_media_path": relative_path}
    if library_id is not None:
        payload["library_id"] = library_id
    job = refiner_enqueue_or_get_job(
        session,
        dedupe_key=f"{REMUX}:{key}",
        job_kind=REMUX,
        payload_json=json.dumps(payload),
        runner_cost=cost,
        priority=priority,
    )
    session.commit()
    return job


def _claim(session: Session, *, owner: str = "w1") -> RefinerJob | None:
    job = claim_next_eligible_refiner_job(
        session,
        lease_owner=owner,
        lease_expires_at=NOW + timedelta(hours=1),
        now=NOW,
        admission=evaluate_work_admission(session, now=NOW),
    )
    session.commit()
    return job


# --- weighting ---------------------------------------------------------------------


def test_resolution_classes_are_bands_not_exact_sizes() -> None:
    assert resolution_class_for_dimensions(width=1024, height=576) == "sd"
    assert resolution_class_for_dimensions(width=1280, height=720) == "720p"
    assert resolution_class_for_dimensions(width=1920, height=1080) == "1080p"
    assert resolution_class_for_dimensions(width=3840, height=2160) == "4k"


def test_a_scope_crop_is_weighted_by_its_width_not_its_height() -> None:
    """1920x800 is a 2.35:1 crop of a 1080p master, not a 720p file.

    Height alone cannot tell it from 1280x720, and weighting a scope film as free would
    put some of the most expensive work in the free tier.
    """

    assert resolution_class_for_dimensions(width=1920, height=800) == "1080p"
    assert resolution_class_for_dimensions(width=3840, height=1600) == "4k"


def test_height_alone_is_the_fallback_when_width_is_missing() -> None:
    assert resolution_class_for_height(480) == "sd"
    assert resolution_class_for_height(720) == "720p"
    assert resolution_class_for_height(1080) == "1080p"
    assert resolution_class_for_height(2160) == "4k"


def test_an_unknown_height_is_undetermined_rather_than_guessed() -> None:
    assert resolution_class_for_height(None) == "undetermined"
    assert resolution_class_for_height(0) == "undetermined"
    assert resolution_class_for_height(-1) == "undetermined"


def test_the_tallest_video_stream_wins_so_cover_art_cannot_downgrade_a_file() -> None:
    """A 4K remux carrying a poster must not be weighted by the poster."""

    streams = [{"height": 300}, {"height": 2160}]

    assert video_height_from_streams(streams) == 2160


def test_a_probe_with_no_usable_height_reports_none(session: Session) -> None:
    assert video_height_from_streams([{"codec_type": "video"}]) is None
    assert video_height_from_streams([{"height": "not-a-number"}]) is None
    assert video_height_from_streams([]) is None


def test_coded_height_is_used_when_height_is_missing() -> None:
    assert video_height_from_streams([{"coded_height": 1080}]) == 1080


def test_an_unknown_class_costs_the_undetermined_weight() -> None:
    budget = RunnerBudget(capacity=4, costs={"1080p": 1, "undetermined": 3})

    assert budget.cost_for("something-else") == 3
    assert budget.cost_for(None) == 3


def test_the_migration_preserves_the_effective_concurrency() -> None:
    # With the shipped costs an expensive file costs one unit, so the same number of them
    # run at once as before.
    assert capacity_from_legacy_concurrency(1) == 1
    assert capacity_from_legacy_concurrency(8) == 8
    assert capacity_from_legacy_concurrency(0) == 1


def test_the_budget_reads_the_operator_row(session: Session) -> None:
    budget = budget_from_settings(session.get(RefinerOperatorSettingsRow, 1))

    assert budget.capacity == 2
    assert budget.cost_for("4k") == 1
    assert budget.cost_for("sd") == 0


# --- the budget at lease time -------------------------------------------------------


def test_the_budget_is_exhausted_by_expensive_work(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    _queue(session, key="a", cost=1, library_id=library.id)
    _queue(session, key="b", cost=1, library_id=library.id)
    _queue(session, key="c", cost=1, library_id=library.id)

    assert _claim(session, owner="w1") is not None
    assert _claim(session, owner="w2") is not None
    # Capacity is 2, both units are spent, so the third waits.
    assert _claim(session, owner="w3") is None


def test_a_zero_cost_file_is_admitted_while_the_budget_is_full(session: Session) -> None:
    """The whole point of weighting rather than counting.

    A flat count would have stalled this SD rip behind two 4K remuxes for no reason —
    it costs the machine nothing.
    """

    library = _library(session, max_concurrent_files=8)
    _queue(session, key="4k-a", cost=1, library_id=library.id)
    _queue(session, key="4k-b", cost=1, library_id=library.id)
    _queue(session, key="sd", cost=0, library_id=library.id)

    assert _claim(session, owner="w1") is not None
    assert _claim(session, owner="w2") is not None

    free = _claim(session, owner="w3")

    assert free is not None
    assert free.runner_cost == 0


def test_capacity_frees_up_when_work_completes(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    _queue(session, key="a", cost=2, library_id=library.id)
    _queue(session, key="b", cost=2, library_id=library.id)

    first = _claim(session, owner="w1")
    assert first is not None
    assert _claim(session, owner="w2") is None

    first.status = RefinerJobStatus.COMPLETED.value
    session.commit()

    assert _claim(session, owner="w2") is not None


# --- per-library cap ----------------------------------------------------------------


def test_a_library_cannot_exceed_its_own_cap_however_cheap_its_files_are(session: Session) -> None:
    """Otherwise one library occupies every worker with free files and starves the rest."""

    library = _library(session, max_concurrent_files=1)
    _queue(session, key="a", cost=0, library_id=library.id)
    _queue(session, key="b", cost=0, library_id=library.id)

    assert _claim(session, owner="w1") is not None
    assert _claim(session, owner="w2") is None


def test_one_library_at_its_cap_does_not_block_another(session: Session) -> None:
    movies = _library(session, name="Movies", max_concurrent_files=1)
    tv = _library(session, name="TV", max_concurrent_files=1)
    _queue(session, key="m1", cost=0, library_id=movies.id)
    _queue(session, key="m2", cost=0, library_id=movies.id)
    _queue(session, key="t1", cost=0, library_id=tv.id)

    assert _claim(session, owner="w1") is not None
    second = _claim(session, owner="w2")

    assert second is not None
    assert json.loads(second.payload_json or "{}")["library_id"] == tv.id


# --- priority and move to top -------------------------------------------------------


def test_higher_priority_is_leased_first(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    _queue(session, key="ordinary", cost=0, library_id=library.id, priority=0)
    urgent = _queue(session, key="urgent", cost=0, library_id=library.id, priority=5)

    claimed = _claim(session)

    assert claimed is not None
    assert claimed.id == urgent.id


def test_equal_priority_keeps_first_in_first_out(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    first = _queue(session, key="first", cost=0, library_id=library.id)
    _queue(session, key="second", cost=0, library_id=library.id)

    claimed = _claim(session)

    assert claimed is not None
    assert claimed.id == first.id


def test_move_to_top_puts_a_queued_job_ahead_of_everything(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    _queue(session, key="a", cost=0, library_id=library.id)
    _queue(session, key="b", cost=0, library_id=library.id)
    last = _queue(session, key="c", cost=0, library_id=library.id)

    assert move_refiner_job_to_top(session, job_id=int(last.id)) == "ok"
    session.commit()

    claimed = _claim(session)

    assert claimed is not None
    assert claimed.id == last.id


def test_two_files_moved_to_the_top_keep_the_order_they_were_moved_in(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    a = _queue(session, key="a", cost=0, library_id=library.id)
    b = _queue(session, key="b", cost=0, library_id=library.id)

    move_refiner_job_to_top(session, job_id=int(a.id))
    move_refiner_job_to_top(session, job_id=int(b.id))
    session.commit()

    claimed = _claim(session)

    assert claimed is not None
    assert claimed.id == b.id


def test_a_running_job_cannot_be_moved_to_the_top(session: Session) -> None:
    """It has already started; a button that appeared to work would be a lie."""

    library = _library(session, max_concurrent_files=8)
    _queue(session, key="a", cost=0, library_id=library.id)
    running = _claim(session)
    assert running is not None

    assert move_refiner_job_to_top(session, job_id=int(running.id)) == "wrong_status"


def test_moving_a_job_that_does_not_exist_reports_that(session: Session) -> None:
    assert move_refiner_job_to_top(session, job_id=9999) == "not_found"


def test_the_queued_job_for_a_path_is_found_and_a_running_one_is_not(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    _queue(session, key="a", cost=0, library_id=library.id, relative_path="Film/film.mkv")

    found = pending_remux_job_for_relative_path(session, relative_path="Film/film.mkv")
    assert found is not None

    assert pending_remux_job_for_relative_path(session, relative_path="Other/other.mkv") is None

    _claim(session)
    assert pending_remux_job_for_relative_path(session, relative_path="Film/film.mkv") is None


def test_a_blank_path_matches_nothing_rather_than_the_first_job(session: Session) -> None:
    library = _library(session, max_concurrent_files=8)
    _queue(session, key="a", cost=0, library_id=library.id)

    assert pending_remux_job_for_relative_path(session, relative_path="   ") is None


def test_jobs_enqueued_without_a_cost_default_to_free(session: Session) -> None:
    """Every existing enqueue site keeps working, and none of them stall the budget."""

    job = refiner_enqueue_or_get_job(session, dedupe_key=f"{REMUX}:legacy", job_kind=REMUX, payload_json="{}")
    session.commit()

    assert job.runner_cost == 0
    assert job.priority == 0
    assert session.scalars(select(RefinerJob)).one().id == job.id
