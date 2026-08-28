"""Permanent guards: module-owned ``job_kind`` prefixes vs the Refiner and Pruner lanes."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_jobs_ops import pruner_enqueue_or_get_job
from mediamop.modules.pruner.worker_loop import process_one_pruner_job
from mediamop.modules.queue_worker.job_kind_boundaries import (
    job_kind_forbidden_on_refiner_lane,
    validate_pruner_worker_handler_registry,
    validate_refiner_worker_handler_registry,
)
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.worker_loop import (
    default_refiner_job_handler_registry,
    process_one_refiner_job,
)

# Legacy lane prefixes still blocked on every queue (see ``job_kind_boundaries``).
# Subber joined Trimmer here when it moved to Deluno: a row left in an older
# install's queue must still be refused, not adopted by whichever lane finds it.
_LEGACY_TRIMMER_JOB = "trimmer.radarr.cleanup_drive.v1"
_LEGACY_SUBBER_JOB = "subber.subtitle_search.tv.v1"


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
        refiner_enqueue_or_get_job(s, dedupe_key="t", job_kind="pruner.probe.v1")
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
        validate_refiner_worker_handler_registry({"pruner.x": lambda _c: None})
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


def test_pruner_enqueue_rejects_foreign_namespaces(session_factory) -> None:
    with session_factory() as s, pytest.raises(ValueError, match="pruner_enqueue_or_get_job refuses"):
        pruner_enqueue_or_get_job(s, dedupe_key="x", job_kind="refiner.compact.v1")
    with session_factory() as s, pytest.raises(ValueError, match="pruner_enqueue_or_get_job refuses"):
        pruner_enqueue_or_get_job(
            s,
            dedupe_key="y",
            job_kind=_LEGACY_TRIMMER_JOB,
        )
    with session_factory() as s, pytest.raises(ValueError, match="pruner_enqueue_or_get_job refuses"):
        pruner_enqueue_or_get_job(
            s,
            dedupe_key="z",
            job_kind=_LEGACY_SUBBER_JOB,
        )
    with session_factory() as s, pytest.raises(ValueError, match="pruner_enqueue_or_get_job refuses"):
        pruner_enqueue_or_get_job(s, dedupe_key="legacy", job_kind="trimmer.legacy.v1")


def test_pruner_enqueue_rejects_unprefixed_job_kind(session_factory) -> None:
    with session_factory() as s, pytest.raises(ValueError, match="pruner_enqueue_or_get_job requires job_kind"):
        pruner_enqueue_or_get_job(s, dedupe_key="u", job_kind="bare.kind")


def test_validate_pruner_worker_handler_registry_rejects_foreign_lane_keys() -> None:
    with pytest.raises(ValueError, match="Pruner worker handler registry"):
        validate_pruner_worker_handler_registry(
            {_LEGACY_TRIMMER_JOB: lambda _c: None},
        )
    with pytest.raises(ValueError, match="Pruner worker handler registry"):
        validate_pruner_worker_handler_registry({"refiner.x.v1": lambda _c: None})
    with pytest.raises(ValueError, match="Pruner worker handler registry"):
        validate_pruner_worker_handler_registry(
            {_LEGACY_SUBBER_JOB: lambda _c: None},
        )


def test_validate_pruner_worker_handler_registry_rejects_unprefixed_keys() -> None:
    with pytest.raises(ValueError, match="Pruner worker handler registry"):
        validate_pruner_worker_handler_registry({"bare.kind": lambda _c: None})


def test_process_one_pruner_job_fails_claimed_row_with_foreign_lane_job_kind(
    session_factory,
    tmp_path,
) -> None:
    """Mis-placed ``pruner_jobs`` rows stamped with another module's prefix must not execute."""

    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=UTC)
    with session_factory() as s:
        s.add(
            PrunerJob(
                dedupe_key="legacy-pruner",
                job_kind="refiner.leaked_on_pruner.v1",
                status=PrunerJobStatus.PENDING.value,
            ),
        )
        s.commit()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(tmp_path / "mmhome"))
    handlers = build_pruner_job_handlers(settings, session_factory)
    out = process_one_pruner_job(
        session_factory,
        lease_owner="t",
        job_handlers=handlers,
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.scalars(select(PrunerJob)).first()
        assert row is not None
        assert row.status == PrunerJobStatus.PENDING.value
        assert row.last_error is not None
        assert "pruner worker refused" in row.last_error


def test_process_one_pruner_job_rejects_unprefixed_job_kind_row(session_factory, tmp_path) -> None:
    """Direct-insert rows without ``pruner.*`` must fail safe on the Pruner worker."""

    t0 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=UTC)
    with session_factory() as s:
        s.add(
            PrunerJob(
                dedupe_key="legacy-pruner-unprefixed",
                job_kind="legacy.unprefixed",
                status=PrunerJobStatus.PENDING.value,
            ),
        )
        s.commit()

    settings = replace(MediaMopSettings.load(), mediamop_home=str(tmp_path / "mmhome"))
    handlers = build_pruner_job_handlers(settings, session_factory)
    out = process_one_pruner_job(
        session_factory,
        lease_owner="t",
        job_handlers=handlers,
        now=t0,
        lease_seconds=3600,
    )
    assert out == "processed"
    with session_factory() as s:
        row = s.scalars(select(PrunerJob)).first()
        assert row is not None
        assert row.status == PrunerJobStatus.PENDING.value
        assert row.last_error is not None
        assert "pruner.* prefix" in row.last_error
