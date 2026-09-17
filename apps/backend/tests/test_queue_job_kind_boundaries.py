"""Permanent guards: module-owned ``job_kind`` prefixes vs the Refiner lane."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.db import Base
from mediamop.modules.queue_worker.job_kind_boundaries import (
    job_kind_forbidden_on_refiner_lane,
    validate_refiner_worker_handler_registry,
)
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.worker_loop import (
    default_refiner_job_handler_registry,
    process_one_refiner_job,
)

# Legacy lane prefixes still blocked on every queue (see ``job_kind_boundaries``).
# Subber and then Pruner joined Trimmer here when they moved to Deluno: a row left in
# an older install's queue must still be refused, not adopted by whichever lane finds it.
_LEGACY_TRIMMER_JOB = "trimmer.radarr.cleanup_drive.v1"
_LEGACY_SUBBER_JOB = "subber.subtitle_search.tv.v1"
_LEGACY_PRUNER_JOB = "pruner.candidate_removal.preview.v1"


@pytest.fixture
def jobs_engine(tmp_path):
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'boundary.sqlite'}"
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30.0},
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(jobs_engine):
    return sessionmaker(
        bind=jobs_engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def test_default_refiner_handler_registry_has_no_foreign_lane_keys() -> None:
    reg = default_refiner_job_handler_registry()
    assert not any(job_kind_forbidden_on_refiner_lane(k) for k in reg)
    assert all(str(k).startswith("refiner.") for k in reg)


def test_refiner_enqueue_rejects_foreign_namespaces(session_factory) -> None:
    with session_factory() as s, pytest.raises(ValueError, match="refiner_enqueue_or_get_job refuses"):
        refiner_enqueue_or_get_job(s, dedupe_key="t", job_kind=_LEGACY_PRUNER_JOB)
    with session_factory() as s, pytest.raises(ValueError, match="refiner_enqueue_or_get_job refuses"):
        refiner_enqueue_or_get_job(s, dedupe_key="legacy", job_kind="trimmer.legacy.v1")
    with session_factory() as s, pytest.raises(ValueError, match="refiner_enqueue_or_get_job refuses"):
        refiner_enqueue_or_get_job(
            s,
            dedupe_key="s",
            job_kind=_LEGACY_SUBBER_JOB,
        )


def test_refiner_enqueue_rejects_unprefixed_job_kind(session_factory) -> None:
    with session_factory() as s, pytest.raises(ValueError, match="refiner_enqueue_or_get_job requires job_kind"):
        refiner_enqueue_or_get_job(s, dedupe_key="u", job_kind="bare.kind")


def test_validate_refiner_worker_handler_registry_rejects_foreign_lane_keys() -> None:
    with pytest.raises(ValueError, match="Refiner worker handler registry"):
        validate_refiner_worker_handler_registry(
            {_LEGACY_TRIMMER_JOB: lambda _c: None},
        )
    with pytest.raises(ValueError, match="Refiner worker handler registry"):
        validate_refiner_worker_handler_registry({_LEGACY_PRUNER_JOB: lambda _c: None})
    with pytest.raises(ValueError, match="Refiner worker handler registry"):
        validate_refiner_worker_handler_registry(
            {_LEGACY_SUBBER_JOB: lambda _c: None},
        )


def test_validate_refiner_worker_handler_registry_rejects_unprefixed_keys() -> None:
    with pytest.raises(ValueError, match="Refiner worker handler registry"):
        validate_refiner_worker_handler_registry({"bare.kind": lambda _c: None})


def test_validate_refiner_worker_handler_registry_accepts_refiner_prefixed_keys() -> None:
    validate_refiner_worker_handler_registry({"refiner.test.mechanics.v1": lambda _c: None})


def test_process_one_refiner_job_fails_claimed_row_in_foreign_lane_without_handler(
    session_factory,
) -> None:
    """Mis-placed ``refiner_jobs`` rows stamped with another module's prefix must not execute."""

    with session_factory() as s:
        s.add(
            RefinerJob(
                dedupe_key="legacy",
                job_kind=_LEGACY_TRIMMER_JOB,
                status=RefinerJobStatus.PENDING.value,
            ),
        )
        s.commit()

    out = process_one_refiner_job(
        session_factory,
        lease_owner="t",
        job_handlers={"refiner.test.other.v1": lambda _c: None},
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.scalars(select(RefinerJob)).first()
        assert row is not None
        assert row.status == RefinerJobStatus.PENDING.value
        assert row.last_error is not None
        assert "refiner worker refused" in row.last_error


def test_process_one_refiner_job_rejects_unprefixed_job_kind_row(session_factory) -> None:
    """Direct-insert legacy rows without ``refiner.*`` must fail safe on the Refiner worker."""

    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=UTC)
    with session_factory() as s:
        s.add(
            RefinerJob(
                dedupe_key="legacy-unprefixed",
                job_kind="legacy.unprefixed",
                status=RefinerJobStatus.PENDING.value,
            ),
        )
        s.commit()

    out = process_one_refiner_job(
        session_factory,
        lease_owner="t",
        job_handlers={"refiner.test.other.v1": lambda _c: None},
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.scalars(select(RefinerJob)).first()
        assert row is not None
        assert row.status == RefinerJobStatus.PENDING.value
        assert row.last_error is not None
        assert "refiner.* prefix" in row.last_error


def test_a_leftover_pruner_row_is_refused_by_the_refiner_worker(session_factory) -> None:
    """Pruner moved to Deluno (#473); a ``pruner.*`` row from an older install must not run."""

    with session_factory() as s:
        s.add(
            RefinerJob(
                dedupe_key="legacy-pruner",
                job_kind=_LEGACY_PRUNER_JOB,
                status=RefinerJobStatus.PENDING.value,
            ),
        )
        s.commit()

    out = process_one_refiner_job(
        session_factory,
        lease_owner="t",
        job_handlers={"refiner.test.other.v1": lambda _c: None},
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.scalars(select(RefinerJob)).first()
        assert row is not None
        assert row.status == RefinerJobStatus.PENDING.value
        assert row.last_error is not None
        assert "refiner worker refused" in row.last_error
