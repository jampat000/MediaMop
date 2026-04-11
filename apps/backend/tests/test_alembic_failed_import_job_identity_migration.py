"""0005 migrates historical refiner.* failed-import job rows to failed_import.* strings."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
    RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    enqueue_radarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
    SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    enqueue_sonarr_failed_import_cleanup_drive_job,
)


@pytest.fixture
def isolated_alembic_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "failed_import_identity_mig_home"
    home.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_FETCHER_WORKER_COUNT", "0")
    return home


def test_0005_migrates_legacy_failed_import_job_rows(
    isolated_alembic_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    monkeypatch.chdir(backend)
    command.upgrade(cfg, "0004_fetcher_failed_import_cleanup_policy")

    settings = MediaMopSettings.load()
    eng = create_engine(settings.sqlalchemy_database_url)
    old_r_kind = "refiner.radarr.failed_import_cleanup_drive.v1"
    old_r_dedupe = "refiner.radarr.failed_import_cleanup_drive:v1"
    old_s_kind = "refiner.sonarr.failed_import_cleanup_drive.v1"
    old_s_dedupe = "refiner.sonarr.failed_import_cleanup_drive:v1"
    other_dedupe = "refiner.other.job:smoke"
    other_kind = "refiner.other.job.v1"

    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO refiner_jobs (dedupe_key, job_kind) VALUES (:d, :k)"),
            {"d": old_r_dedupe, "k": old_r_kind},
        )
        conn.execute(
            text("INSERT INTO refiner_jobs (dedupe_key, job_kind) VALUES (:d, :k)"),
            {"d": old_s_dedupe, "k": old_s_kind},
        )
        conn.execute(
            text("INSERT INTO refiner_jobs (dedupe_key, job_kind) VALUES (:d, :k)"),
            {"d": other_dedupe, "k": other_kind},
        )

    command.upgrade(cfg, "head")

    with eng.connect() as conn:
        refiner_rows = conn.execute(text("SELECT dedupe_key, job_kind FROM refiner_jobs ORDER BY id")).fetchall()
        fetcher_rows = conn.execute(text("SELECT dedupe_key, job_kind FROM fetcher_jobs ORDER BY id")).fetchall()
    rset = {(str(r[0]), str(r[1])) for r in refiner_rows}
    fset = {(str(r[0]), str(r[1])) for r in fetcher_rows}

    assert (RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY, FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE) in fset
    assert (SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY, FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE) in fset
    assert (other_dedupe, other_kind) in rset
    assert (old_r_dedupe, old_r_kind) not in fset
    assert (old_s_dedupe, old_s_kind) not in fset


def test_enqueue_writes_only_failed_import_identity_strings(
    isolated_alembic_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    monkeypatch.chdir(backend)
    command.upgrade(cfg, "head")

    settings = MediaMopSettings.load()
    factory = sessionmaker(bind=create_db_engine(settings), expire_on_commit=False)
    with factory() as session:
        r = enqueue_radarr_failed_import_cleanup_drive_job(session)
        s = enqueue_sonarr_failed_import_cleanup_drive_job(session)
        session.commit()
    assert r.job_kind == FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE
    assert r.dedupe_key == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY
    assert s.job_kind == FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE
    assert s.dedupe_key == SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY
    assert "refiner." not in r.job_kind
    assert "refiner." not in s.job_kind
    assert "refiner." not in r.dedupe_key
    assert "refiner." not in s.dedupe_key
