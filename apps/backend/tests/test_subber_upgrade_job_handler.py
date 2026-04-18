"""Tests for ``subber.subtitle_upgrade.v1`` handler."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import Base
from mediamop.modules.subber.subber_job_handlers import build_subber_job_handlers
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_SUBTITLE_UPGRADE
from mediamop.modules.subber.subber_jobs_model import SubberJob
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.modules.subber.worker_loop import process_one_subber_job

import mediamop.modules.subber.subber_jobs_model  # noqa: F401
import mediamop.modules.subber.subber_settings_model  # noqa: F401
import mediamop.modules.subber.subber_subtitle_state_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def session_factory(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'sub_upgrade.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)


@patch("mediamop.modules.subber.subber_upgrade_job_handler.search_and_download_subtitle", return_value=False)
def test_upgrade_job_noop_when_disabled(mock_dl, session_factory) -> None:
    with session_factory() as s:
        s.add(SubberSettingsRow(id=1, enabled=True, upgrade_enabled=False))
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="up:1",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_UPGRADE,
            payload_json=json.dumps({}),
        )
        s.commit()
    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    process_one_subber_job(session_factory, lease_owner="u1", job_handlers=handlers, now=t0, lease_seconds=600)
    assert not mock_dl.called


@patch("mediamop.modules.subber.subber_upgrade_job_handler.get_candidates_for_upgrade")
@patch("mediamop.modules.subber.subber_upgrade_job_handler.subber_any_search_configured", return_value=True)
@patch("mediamop.modules.subber.subber_upgrade_job_handler.search_and_download_subtitle", return_value=True)
def test_upgrade_runs_when_enabled(mock_dl, _mock_cfg, mock_cand, session_factory, tmp_path: Path) -> None:
    srt = tmp_path / "f.en.srt"
    srt.write_bytes(b"1\n")
    with session_factory() as s:
        st = SubberSubtitleState(
            media_scope="tv",
            file_path="/v/a.mkv",
            language_code="en",
            status="found",
            subtitle_path=str(srt),
            search_count=1,
        )
        s.add(SubberSettingsRow(id=1, enabled=True, upgrade_enabled=True))
        s.add(st)
        s.commit()
        sid = int(st.id)
        mock_cand.return_value = [s.get(SubberSubtitleState, sid)]
        subber_enqueue_or_get_job(
            s,
            dedupe_key="up:2",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_UPGRADE,
            payload_json=json.dumps({}),
        )
        s.commit()
    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    process_one_subber_job(session_factory, lease_owner="u2", job_handlers=handlers, now=t0, lease_seconds=600)
    assert mock_dl.called
    assert mock_cand.called
    with session_factory() as s:
        row = s.get(SubberSubtitleState, sid)
        assert row is not None


def test_upgrade_job_kind_registered() -> None:
    from mediamop.modules.subber.subber_job_kinds import ALL_SUBBER_PRODUCTION_JOB_KINDS

    assert "subber.subtitle_upgrade.v1" in ALL_SUBBER_PRODUCTION_JOB_KINDS


@patch("mediamop.modules.subber.subber_upgrade_job_handler.search_and_download_subtitle", return_value=False)
def test_upgrade_handler_skips_when_subber_disabled(mock_dl, session_factory) -> None:
    with session_factory() as s:
        s.add(SubberSettingsRow(id=1, enabled=False, upgrade_enabled=True))
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="up:disabled-subber",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_UPGRADE,
            payload_json=json.dumps({}),
        )
        s.commit()
    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 1, 2, tzinfo=timezone.utc)
    process_one_subber_job(session_factory, lease_owner="u3", job_handlers=handlers, now=t0, lease_seconds=600)
    assert not mock_dl.called


def test_upgrade_handler_runs_when_enabled_with_candidates(session_factory, tmp_path: Path) -> None:
    from sqlalchemy import select

    from mediamop.platform.activity import constants as C
    from mediamop.platform.activity.models import ActivityEvent

    srt = tmp_path / "g.en.srt"
    srt.write_bytes(b"1\n")
    with session_factory() as s:
        st = SubberSubtitleState(
            media_scope="tv",
            file_path="/v/b.mkv",
            language_code="en",
            status="found",
            subtitle_path=str(srt),
            search_count=1,
        )
        s.add(SubberSettingsRow(id=1, enabled=True, upgrade_enabled=True))
        s.add(st)
        s.commit()
        sid = int(st.id)
        subber_enqueue_or_get_job(
            s,
            dedupe_key="up:3",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_UPGRADE,
            payload_json=json.dumps({}),
        )
        s.commit()

    def _fake_candidates(session, _since_days: int):
        r = session.get(SubberSubtitleState, sid)
        return [r] if r is not None else []

    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 1, 3, tzinfo=timezone.utc)
    with (
        patch(
            "mediamop.modules.subber.subber_upgrade_job_handler.search_and_download_subtitle",
            return_value=True,
        ) as mock_dl,
        patch(
            "mediamop.modules.subber.subber_upgrade_job_handler.subber_any_search_configured",
            return_value=True,
        ),
        patch(
            "mediamop.modules.subber.subber_upgrade_job_handler.get_candidates_for_upgrade",
            side_effect=_fake_candidates,
        ),
    ):
        process_one_subber_job(session_factory, lease_owner="u4", job_handlers=handlers, now=t0, lease_seconds=600)
    assert mock_dl.called
    with session_factory() as s:
        row = s.get(SubberSubtitleState, sid)
        assert row is not None
        assert int(row.upgrade_count or 0) >= 1
        assert row.upgraded_at is not None
    with session_factory() as s:
        ev = s.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.event_type == C.SUBBER_SUBTITLE_UPGRADE_COMPLETED)
            .order_by(ActivityEvent.id.desc()),
        ).first()
        assert ev is not None
        assert "finished" in (ev.title or "").lower()
