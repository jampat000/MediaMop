from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from alembic import command
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_constants import MEDIA_SCOPE_MOVIES, RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import (
    PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
    PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
)
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_jobs_ops import pruner_enqueue_or_get_job
from mediamop.modules.pruner.pruner_overview_stats_service import build_pruner_overview_stats
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.worker_loop import process_one_pruner_job
from mediamop.modules.refiner.file_remux_pass import run as refiner_run
from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.refiner_operator_settings_model import RefinerOperatorSettingsRow
from mediamop.modules.refiner.refiner_overview_stats_service import build_refiner_overview_stats
from mediamop.modules.refiner.worker_loop import process_one_refiner_job
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.refiner_library_fixtures import seed_refiner_libraries


@pytest.fixture
def isolated_session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sessionmaker[Session]:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_e2e_workflows")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(cfg, "head")
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def _fake_probe() -> dict[str, object]:
    return {
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "tags": {"language": "eng"},
            },
        ],
    }


def test_refiner_file_reaches_output_cleanup_and_stats(
    isolated_session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MediaMopSettings.load()
    watched = tmp_path / "watched"
    output = tmp_path / "output"
    work = tmp_path / "work"
    release = watched / "Movie.Release"
    for path in (release, output, work):
        path.mkdir(parents=True)
    source = release / "movie.mkv"
    source.write_bytes(b"x" * 2048)

    with isolated_session_factory() as session, session.begin():
        # Processing resolves paths from refiner_libraries, which is the only store now
        # (#363), so this seeds them directly.
        seed_refiner_libraries(
            session,
            watched_folder=str(watched),
            work_folder=str(work),
            output_folder=str(output),
            min_file_age_seconds=0,
            file_detection_interval_seconds=0,
        )
        session.merge(
            RefinerOperatorSettingsRow(
                id=1,
                min_file_age_seconds=0,
                refiner_min_input_file_size_mb=0,
                minimum_free_disk_space_mb=1,
            ),
        )
        refiner_enqueue_or_get_job(
            session,
            dedupe_key="e2e-refiner-copy-cleanup",
            job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
            payload_json=json.dumps(
                {"relative_media_path": "Movie.Release/movie.mkv", "media_scope": "movie"},
                separators=(",", ":"),
            ),
        )

    monkeypatch.setattr(refiner_run, "ffprobe_json", lambda path, mediamop_home, **kwargs: _fake_probe())
    monkeypatch.setattr(refiner_run, "resolve_ffprobe_ffmpeg", lambda *, mediamop_home: ("ffprobe", "ffmpeg"))
    monkeypatch.setattr(refiner_run, "is_remux_required", lambda *_args, **_kwargs: False)

    handlers = build_refiner_job_handlers(settings, isolated_session_factory)
    assert (
        process_one_refiner_job(
            isolated_session_factory,
            lease_owner="pytest-refiner",
            job_handlers=handlers,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        == "processed"
    )

    copied = output / "Movie.Release" / "movie.mkv"
    assert copied.read_bytes() == b"x" * 2048
    assert not source.exists()
    assert not release.exists()
    with isolated_session_factory() as session:
        job = session.scalars(select(RefinerJob)).one()
        stats = build_refiner_overview_stats(session)
    assert job.status == RefinerJobStatus.COMPLETED.value
    assert stats.files_processed == 1
    assert stats.already_optimized_count == 1
    assert stats.output_written_count == 0


def test_pruner_preview_apply_reaches_terminal_state_and_stats(
    isolated_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEDIAMOP_PRUNER_APPLY_ENABLED", "1")
    settings = replace(MediaMopSettings.load(), pruner_apply_enabled=True)
    deleted: list[str] = []

    with isolated_session_factory() as session, session.begin():
        inst = create_server_instance(
            session,
            settings,
            provider="plex",
            display_name="Living room",
            base_url="http://plex.test:32400",
            credentials_secrets={"auth_token": "plex-token"},
        )
        server_instance_id = int(inst.id)
        pruner_enqueue_or_get_job(
            session,
            dedupe_key="e2e-pruner-preview",
            job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
            payload_json=json.dumps(
                {
                    "server_instance_id": server_instance_id,
                    "media_scope": MEDIA_SCOPE_MOVIES,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                    "trigger": "manual",
                },
                separators=(",", ":"),
            ),
        )

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_preview_job_handler.preview_payload_json",
        lambda **_kwargs: (
            "success",
            None,
            [{"item_id": "101", "title": "Gone"}, {"item_id": "404", "title": "Already gone"}],
            False,
        ),
    )

    handlers = build_pruner_job_handlers(settings, isolated_session_factory)
    assert (
        process_one_pruner_job(
            isolated_session_factory,
            lease_owner="pytest-pruner-preview",
            job_handlers=handlers,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        == "processed"
    )

    with isolated_session_factory() as session:
        preview = session.scalars(select(PrunerPreviewRun)).one()
        pruner_enqueue_or_get_job(
            session,
            dedupe_key="e2e-pruner-apply",
            job_kind=PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
            payload_json=json.dumps(
                {
                    "preview_run_uuid": preview.preview_run_id,
                    "server_instance_id": server_instance_id,
                    "media_scope": MEDIA_SCOPE_MOVIES,
                    "rule_family_id": RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
                },
                separators=(",", ":"),
            ),
        )
        session.commit()

    def _delete(**kwargs: object) -> tuple[int, str | None]:
        rating_key = str(kwargs["rating_key"])
        deleted.append(rating_key)
        return (404, None) if rating_key == "404" else (200, None)

    monkeypatch.setattr("mediamop.modules.pruner.pruner_apply_job_handler.plex_delete_library_metadata", _delete)

    assert (
        process_one_pruner_job(
            isolated_session_factory,
            lease_owner="pytest-pruner-apply",
            job_handlers=handlers,
            now=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        )
        == "processed"
    )

    with isolated_session_factory() as session:
        jobs = list(session.scalars(select(PrunerJob).order_by(PrunerJob.id.asc())).all())
        stats = build_pruner_overview_stats(session)
    assert [job.status for job in jobs] == [PrunerJobStatus.COMPLETED.value, PrunerJobStatus.COMPLETED.value]
    assert deleted == ["101", "404"]
    assert stats.preview_runs == 1
    assert stats.apply_runs == 1
    assert stats.items_removed == 1
    assert stats.items_skipped == 1
