from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_crash_recovery import cleanup_refiner_partial_output_files
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.platform.jobs.startup_recovery import recover_incomplete_jobs_after_startup


def _session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'startup_recovery.sqlite'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def test_startup_recovery_requeues_leased_jobs_with_attempts_remaining(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path)
    now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
    with factory() as session:
        with session.begin():
            session.add_all(
                [
                    RefinerJob(
                        dedupe_key="refiner-recover",
                        job_kind="refiner.test.v1",
                        status=RefinerJobStatus.LEASED.value,
                        lease_owner="dead-refiner",
                        lease_expires_at=now + timedelta(hours=1),
                        attempt_count=1,
                        max_attempts=3,
                    ),
                    PrunerJob(
                        dedupe_key="pruner-recover",
                        job_kind="pruner.test.v1",
                        status=PrunerJobStatus.LEASED.value,
                        lease_owner="dead-pruner",
                        lease_expires_at=now + timedelta(hours=1),
                        attempt_count=1,
                        max_attempts=2,
                    ),
                    SubberJob(
                        dedupe_key="subber-recover",
                        job_kind="subber.test.v1",
                        status=SubberJobStatus.LEASED.value,
                        lease_owner="dead-subber",
                        lease_expires_at=now + timedelta(hours=1),
                        attempt_count=0,
                        max_attempts=1,
                    ),
                ],
            )

    with factory() as session:
        with session.begin():
            result = recover_incomplete_jobs_after_startup(session, now=now)

    assert result.refiner_requeued == 1
    assert result.pruner_requeued == 1
    assert result.subber_requeued == 1
    with factory() as session:
        for row in (
            session.get(RefinerJob, 1),
            session.get(PrunerJob, 1),
            session.get(SubberJob, 1),
        ):
            assert row is not None
            assert row.status == "pending"
            assert row.lease_owner is None
            assert row.lease_expires_at is None
            assert "queued for another safe attempt" in str(row.last_error)


def test_startup_recovery_fails_leased_jobs_after_final_attempt(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path)
    now = datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc)
    with factory() as session:
        with session.begin():
            session.add(
                RefinerJob(
                    dedupe_key="refiner-final",
                    job_kind="refiner.test.v1",
                    status=RefinerJobStatus.LEASED.value,
                    lease_owner="dead-refiner",
                    lease_expires_at=now + timedelta(hours=1),
                    attempt_count=3,
                    max_attempts=3,
                ),
            )

    with factory() as session:
        with session.begin():
            result = recover_incomplete_jobs_after_startup(session, now=now)

    assert result.refiner_failed == 1
    with factory() as session:
        row = session.get(RefinerJob, 1)
        assert row is not None
        assert row.status == RefinerJobStatus.FAILED.value
        assert row.lease_owner is None
        assert row.lease_expires_at is None
        assert "marked failed" in str(row.last_error)


def test_startup_refiner_recovery_removes_hidden_partial_outputs(tmp_path: Path) -> None:
    factory = _session_factory(tmp_path)
    output = tmp_path / "output"
    nested = output / "Movie"
    nested.mkdir(parents=True)
    partial = nested / ".movie.mkv.abc.partial"
    partial.write_bytes(b"partial")
    final = nested / "movie.mkv"
    final.write_bytes(b"complete")

    settings = MediaMopSettings.load()
    with factory() as session:
        with session.begin():
            session.add(RefinerPathSettingsRow(id=1, refiner_output_folder=str(output), refiner_work_folder="", refiner_watched_folder=""))

    with factory() as session:
        removed = cleanup_refiner_partial_output_files(session, settings)

    assert removed == 1
    assert not partial.exists()
    assert final.read_bytes() == b"complete"
