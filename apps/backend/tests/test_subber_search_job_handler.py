"""Unit-style tests for ``subber.subtitle_search.*.v1`` handlers."""

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
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
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
    url = f"sqlite:///{tmp_path / 'sub_search.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)


def _seed_settings(session: Session) -> None:
    session.add(SubberSettingsRow(id=1, enabled=True))
    session.commit()


def test_subtitle_search_skips_when_found_and_file_exists(session_factory, tmp_path: Path) -> None:
    srt = tmp_path / "x.en.srt"
    srt.write_text("1\n", encoding="utf-8")
    with session_factory() as s:
        _seed_settings(s)
        st = SubberSubtitleState(
            media_scope="tv",
            file_path="/v/a.mkv",
            language_code="en",
            status="found",
            subtitle_path=str(srt),
            search_count=0,
        )
        s.add(st)
        s.commit()
        sid = int(st.id)
        subber_enqueue_or_get_job(
            s,
            dedupe_key="t:search:1",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
            payload_json=json.dumps({"state_id": sid}),
        )
        s.commit()

    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert (
        process_one_subber_job(
            session_factory,
            lease_owner="u1",
            job_handlers=handlers,
            now=t0,
            lease_seconds=600,
        )
        == "processed"
    )
    with session_factory() as s:
        job = s.scalars(select(SubberJob)).first()
        assert job is not None
        assert job.status == SubberJobStatus.COMPLETED.value


def test_subtitle_search_marks_skipped_at_search_cap(session_factory) -> None:
    with session_factory() as s:
        _seed_settings(s)
        st = SubberSubtitleState(
            media_scope="tv",
            file_path="/v/b.mkv",
            language_code="en",
            status="missing",
            search_count=5,
        )
        s.add(st)
        s.commit()
        sid = int(st.id)
        subber_enqueue_or_get_job(
            s,
            dedupe_key="t:search:2",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
            payload_json=json.dumps({"state_id": sid}),
        )
        s.commit()

    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    process_one_subber_job(session_factory, lease_owner="u2", job_handlers=handlers, now=t0, lease_seconds=600)
    with session_factory() as s:
        row = s.get(SubberSubtitleState, sid)
        assert row is not None
        assert row.status == "skipped"


@patch("mediamop.modules.subber.subber_search_job_handler.opensubtitles_configured", return_value=True)
@patch("mediamop.modules.subber.subber_search_job_handler.search_and_download_subtitle")
def test_subtitle_search_calls_download(mock_dl, _mock_os_cfg, session_factory) -> None:
    mock_dl.return_value = True
    with session_factory() as s:
        _seed_settings(s)
        st = SubberSubtitleState(
            media_scope="tv",
            file_path="/v/c.mkv",
            language_code="en",
            status="missing",
            search_count=0,
        )
        s.add(st)
        s.commit()
        sid = int(st.id)
        subber_enqueue_or_get_job(
            s,
            dedupe_key="t:search:3",
            job_kind=SUBBER_JOB_KIND_SUBTITLE_SEARCH_TV,
            payload_json=json.dumps({"state_id": sid}),
        )
        s.commit()

    settings = MediaMopSettings.load()
    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    process_one_subber_job(session_factory, lease_owner="u3", job_handlers=handlers, now=t0, lease_seconds=600)
    assert mock_dl.called
