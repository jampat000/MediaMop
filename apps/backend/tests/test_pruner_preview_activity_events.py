"""Preview job activity: outcome-specific event types (no fake success for unsupported)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import mediamop.modules.pruner.pruner_jobs_model  # noqa: F401
import mediamop.modules.pruner.pruner_preview_run_model  # noqa: F401
import mediamop.modules.pruner.pruner_scope_settings_model  # noqa: F401
import mediamop.modules.pruner.pruner_server_instance_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_instances_service import create_server_instance
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.pruner.pruner_preview_run_model import PrunerPreviewRun
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "mmhome_preview_act"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    monkeypatch.setenv("MEDIAMOP_FETCHER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_PRUNER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_SUBBER_WORKER_COUNT", "0")
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def session_factory(_isolated) -> sessionmaker[Session]:
    settings = MediaMopSettings.load()
    return create_session_factory(create_db_engine(settings))


def test_plex_preview_missing_primary_records_success_activity(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="plex",
                display_name="Plex",
                base_url="http://plex.test:32400",
                credentials_secrets={"auth_token": "t"},
            )
            sid = int(inst.id)

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_media_library.list_plex_missing_thumb_candidates",
        lambda **_kw: ([{"item_id": "42", "granularity": "episode", "episode_title": "Pilot"}], False),
    )

    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="preview-activity-test-job",
                job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND]
    fn(
        PrunerJobWorkContext(
            id=job_id,
            job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
            payload_json=json.dumps({"server_instance_id": sid, "media_scope": "tv"}),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.module == "pruner")
            .order_by(ActivityEvent.id.desc()),
        ).first()
        assert evt is not None
        assert evt.event_type == C.PRUNER_PREVIEW_SUCCEEDED
        detail = json.loads(evt.detail or "{}")
        assert detail.get("trigger") == "manual"
        assert detail.get("candidate_count") == 1
        assert int(detail.get("plex_missing_primary_item_cap") or 0) >= 1
        assert "plex_missing_primary_cap_note" in detail

        row = s.scalars(select(PrunerPreviewRun).where(PrunerPreviewRun.server_instance_id == sid)).first()
        assert row is not None
        assert row.outcome == "success"
        assert row.candidate_count == 1
        assert "42" in (row.candidates_json or "")


def test_scheduled_preview_activity_title_and_detail_trigger(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="plex",
                display_name="Plex Sched",
                base_url="http://plex-sched.test:32400",
                credentials_secrets={"auth_token": "t"},
            )
            sid = int(inst.id)

    monkeypatch.setattr(
        "mediamop.modules.pruner.pruner_media_library.list_plex_missing_thumb_candidates",
        lambda **_kw: ([], False),
    )

    with session_factory() as s:
        with s.begin():
            job_row = PrunerJob(
                dedupe_key="preview-activity-scheduled-job",
                job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
                status=PrunerJobStatus.COMPLETED.value,
            )
            s.add(job_row)
            s.flush()
            job_id = int(job_row.id)

    handlers = build_pruner_job_handlers(settings, session_factory)
    fn = handlers[PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND]
    fn(
        PrunerJobWorkContext(
            id=job_id,
            job_kind=PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
            payload_json=json.dumps(
                {"server_instance_id": sid, "media_scope": "tv", "trigger": "scheduled"},
            ),
            lease_owner="pytest",
        ),
    )

    with session_factory() as s:
        evt = s.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.module == "pruner")
            .order_by(ActivityEvent.id.desc()),
        ).first()
        assert evt is not None
        assert evt.title.startswith("Scheduled Pruner preview (missing primary):")
        detail = json.loads(evt.detail or "{}")
        assert detail.get("trigger") == "scheduled"
