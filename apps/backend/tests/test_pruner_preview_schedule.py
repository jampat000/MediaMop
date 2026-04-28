"""Per-(server_instance_id, media_scope) scheduled Pruner preview enqueue — isolation + due contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
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
from mediamop.modules.pruner.pruner_constants import (
    MEDIA_SCOPE_MOVIES,
    MEDIA_SCOPE_TV,
    RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
    RULE_FAMILY_WATCHED_MOVIES_REPORTED,
)
from mediamop.modules.pruner.pruner_instances_service import create_server_instance, get_scope_settings
from mediamop.modules.pruner.pruner_job_kinds import PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob
from mediamop.modules.pruner.pruner_preview_schedule_enqueue import run_pruner_preview_schedule_enqueue_tick
from mediamop.modules.pruner.pruner_scope_settings_model import PrunerScopeSettings


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sessionmaker[Session]:
    home = tmp_path / "mmhome_pruner_sched"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_PRUNER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_SUBBER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_PRUNER_PREVIEW_SCHEDULE_ENQUEUE_ENABLED", "0")
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    command.upgrade(cfg, "head")
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _scope(
    session: Session,
    *,
    instance_id: int,
    media_scope: str,
) -> PrunerScopeSettings:
    row = get_scope_settings(session, server_instance_id=instance_id, media_scope=media_scope)
    assert row is not None
    return row


def test_scheduled_tick_skips_disabled_instance(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="emby",
                display_name="Off",
                base_url="http://off.test",
                credentials_secrets={"api_key": "x"},
            )
            inst.enabled = False
            sid = int(inst.id)
            tv = _scope(s, instance_id=sid, media_scope=MEDIA_SCOPE_TV)
            tv.scheduled_preview_enabled = True
            tv.scheduled_preview_interval_seconds = 60
            tv.last_scheduled_preview_enqueued_at = None
    n = run_pruner_preview_schedule_enqueue_tick(session_factory, now=datetime.now(timezone.utc))
    assert n == 0


def test_scheduled_tick_skips_when_rule_disabled(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="emby",
                display_name="On",
                base_url="http://on.test",
                credentials_secrets={"api_key": "x"},
            )
            sid = int(inst.id)
            tv = _scope(s, instance_id=sid, media_scope=MEDIA_SCOPE_TV)
            tv.scheduled_preview_enabled = True
            tv.scheduled_preview_interval_seconds = 60
            tv.missing_primary_media_reported_enabled = False
            tv.last_scheduled_preview_enqueued_at = None
    assert run_pruner_preview_schedule_enqueue_tick(session_factory, now=datetime.now(timezone.utc)) == 0


def test_two_same_provider_instances_independent_due(session_factory: sessionmaker[Session]) -> None:
    """Instance B not due must not block instance A from enqueueing."""

    settings = MediaMopSettings.load()
    t0 = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            a = create_server_instance(
                s,
                settings,
                provider="emby",
                display_name="A",
                base_url="http://a.test",
                credentials_secrets={"api_key": "a"},
            )
            b = create_server_instance(
                s,
                settings,
                provider="emby",
                display_name="B",
                base_url="http://b.test",
                credentials_secrets={"api_key": "b"},
            )
            id_a, id_b = int(a.id), int(b.id)
            tv_a = _scope(s, instance_id=id_a, media_scope=MEDIA_SCOPE_TV)
            tv_a.scheduled_preview_enabled = True
            tv_a.scheduled_preview_interval_seconds = 60
            tv_a.last_scheduled_preview_enqueued_at = None
            tv_b = _scope(s, instance_id=id_b, media_scope=MEDIA_SCOPE_TV)
            tv_b.scheduled_preview_enabled = True
            tv_b.scheduled_preview_interval_seconds = 3600
            tv_b.last_scheduled_preview_enqueued_at = t0

    now = t0.replace(hour=12, minute=2)
    n = run_pruner_preview_schedule_enqueue_tick(session_factory, now=now)
    assert n == 1
    with session_factory() as s:
        ja = s.scalars(select(PrunerJob).where(PrunerJob.job_kind == PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND)).all()
        assert len(ja) == 1
        payload = json.loads(ja[0].payload_json or "{}")
        assert payload["server_instance_id"] == id_a
        assert payload["media_scope"] == MEDIA_SCOPE_TV
        assert payload["rule_family_id"] == RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED
        assert payload["trigger"] == "scheduled"
        tv_a2 = _scope(s, instance_id=id_a, media_scope=MEDIA_SCOPE_TV)
        tv_b2 = _scope(s, instance_id=id_b, media_scope=MEDIA_SCOPE_TV)
        assert tv_a2.last_scheduled_preview_enqueued_at is not None
        lb = tv_b2.last_scheduled_preview_enqueued_at
        assert lb is not None
        assert _as_utc(lb) == t0


def test_tv_and_movies_same_instance_both_enqueue_when_due(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="Dual",
                base_url="http://dual.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            for scope in (MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES):
                row = _scope(s, instance_id=sid, media_scope=scope)
                row.scheduled_preview_enabled = True
                row.scheduled_preview_interval_seconds = 60
                row.last_scheduled_preview_enqueued_at = None

    n = run_pruner_preview_schedule_enqueue_tick(session_factory, now=datetime.now(timezone.utc))
    assert n == 2
    with session_factory() as s:
        jobs = s.scalars(select(PrunerJob).where(PrunerJob.job_kind == PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND)).all()
        scopes = {json.loads(j.payload_json or "{}")["media_scope"] for j in jobs}
        assert scopes == {MEDIA_SCOPE_TV, MEDIA_SCOPE_MOVIES}
        rules = {json.loads(j.payload_json or "{}")["rule_family_id"] for j in jobs}
        assert rules == {RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED}


def test_scheduled_tick_enqueues_non_missing_primary_rule_family(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="Movies",
                base_url="http://movies.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            movies = _scope(s, instance_id=sid, media_scope=MEDIA_SCOPE_MOVIES)
            movies.scheduled_preview_enabled = True
            movies.scheduled_preview_interval_seconds = 60
            movies.missing_primary_media_reported_enabled = False
            movies.watched_movies_reported_enabled = True
            movies.last_scheduled_preview_enqueued_at = None

    n = run_pruner_preview_schedule_enqueue_tick(session_factory, now=datetime.now(timezone.utc))

    assert n == 1
    with session_factory() as s:
        job = s.scalars(select(PrunerJob).where(PrunerJob.job_kind == PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND)).one()
        payload = json.loads(job.payload_json or "{}")
        assert payload == {
            "server_instance_id": sid,
            "media_scope": MEDIA_SCOPE_MOVIES,
            "rule_family_id": RULE_FAMILY_WATCHED_MOVIES_REPORTED,
            "trigger": "scheduled",
        }


def test_scheduled_tick_enqueues_one_job_per_enabled_rule_family(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="jellyfin",
                display_name="Multi",
                base_url="http://multi.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            movies = _scope(s, instance_id=sid, media_scope=MEDIA_SCOPE_MOVIES)
            movies.scheduled_preview_enabled = True
            movies.scheduled_preview_interval_seconds = 60
            movies.missing_primary_media_reported_enabled = True
            movies.watched_movies_reported_enabled = True
            movies.last_scheduled_preview_enqueued_at = None

    n = run_pruner_preview_schedule_enqueue_tick(session_factory, now=datetime.now(timezone.utc))

    assert n == 2
    with session_factory() as s:
        jobs = s.scalars(select(PrunerJob).where(PrunerJob.job_kind == PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND)).all()
        rules = {json.loads(j.payload_json or "{}")["rule_family_id"] for j in jobs}
        assert rules == {RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED, RULE_FAMILY_WATCHED_MOVIES_REPORTED}


def test_second_tick_not_due_until_own_interval_elapses(session_factory: sessionmaker[Session]) -> None:
    settings = MediaMopSettings.load()
    t0 = datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc)
    with session_factory() as s:
        with s.begin():
            inst = create_server_instance(
                s,
                settings,
                provider="emby",
                display_name="Cadence",
                base_url="http://cad.test",
                credentials_secrets={"api_key": "k"},
            )
            sid = int(inst.id)
            tv = _scope(s, instance_id=sid, media_scope=MEDIA_SCOPE_TV)
            tv.scheduled_preview_enabled = True
            tv.scheduled_preview_interval_seconds = 120
            tv.last_scheduled_preview_enqueued_at = None

    assert run_pruner_preview_schedule_enqueue_tick(session_factory, now=t0) == 1
    assert run_pruner_preview_schedule_enqueue_tick(session_factory, now=t0.replace(minute=1)) == 0
    assert run_pruner_preview_schedule_enqueue_tick(session_factory, now=t0.replace(minute=3)) == 1
