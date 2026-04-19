"""Tests for ``subber.library_sync.{tv,movies}.v1`` handlers."""

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
from mediamop.modules.subber.subber_credentials_crypto import encrypt_subber_credentials_json
from mediamop.modules.subber.subber_job_handlers import build_subber_job_handlers
from mediamop.modules.subber.subber_job_kinds import SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES, SUBBER_JOB_KIND_LIBRARY_SYNC_TV
from mediamop.modules.subber.subber_jobs_ops import subber_enqueue_or_get_job
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.modules.subber.subber_subtitle_state_service import upsert_subtitle_state
from mediamop.modules.subber.worker_loop import process_one_subber_job
from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

import mediamop.modules.subber.subber_jobs_model  # noqa: F401
import mediamop.modules.subber.subber_settings_model  # noqa: F401
import mediamop.modules.subber.subber_subtitle_state_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture
def session_factory(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'lib_sync.sqlite'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)


def _radarr_row(settings: MediaMopSettings, *, url: str = "http://radarr.test") -> SubberSettingsRow:
    ct = encrypt_subber_credentials_json(
        settings,
        json.dumps({"provider": "radarr", "secrets": {"api_key": "secret-r"}}),
    )
    return SubberSettingsRow(
        id=1,
        enabled=True,
        radarr_base_url=url,
        radarr_credentials_ciphertext=ct,
        language_preferences_json='["en"]',
    )


def _sonarr_row(settings: MediaMopSettings, *, url: str = "http://sonarr.test") -> SubberSettingsRow:
    ct = encrypt_subber_credentials_json(
        settings,
        json.dumps({"provider": "sonarr", "secrets": {"api_key": "secret-s"}}),
    )
    return SubberSettingsRow(
        id=1,
        enabled=True,
        sonarr_base_url=url,
        sonarr_credentials_ciphertext=ct,
        language_preferences_json='["en"]',
    )


def test_library_sync_movies_upserts_and_detects_srt(session_factory, tmp_path: Path) -> None:
    settings = MediaMopSettings.load()
    mkv = tmp_path / "Movie.2023.mkv"
    mkv.parent.mkdir(parents=True, exist_ok=True)
    mkv.write_bytes(b"x")
    srt = tmp_path / "Movie.2023.en.srt"
    srt.write_text("1\n", encoding="utf-8")
    movies_payload = [
        {
            "id": 9,
            "title": "Movie",
            "year": 2023,
            "hasFile": True,
            "movieFile": {"path": str(mkv)},
        },
    ]

    with session_factory() as s:
        s.add(_radarr_row(settings))
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="lsync:movies:1",
            job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES,
            payload_json="{}",
        )
        s.commit()

    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with patch("mediamop.modules.subber.subber_library_sync_job_handler.get_radarr_movies", return_value=movies_payload):
        assert (
            process_one_subber_job(
                session_factory,
                lease_owner="ls1",
                job_handlers=handlers,
                now=t0,
                lease_seconds=600,
            )
            == "processed"
        )

    with session_factory() as s:
        rows = list(s.scalars(select(SubberSubtitleState)).all())
        assert len(rows) == 1
        r = rows[0]
        assert r.media_scope == "movies"
        assert r.file_path == str(mkv)
        assert r.language_code == "en"
        assert r.status == "found"
        assert r.subtitle_path == str(srt)
        assert r.source == "sync"
        assert r.radarr_movie_id == 9
        ev = s.scalars(select(ActivityEvent).where(ActivityEvent.event_type == C.SUBBER_LIBRARY_SYNC_COMPLETED)).first()
        assert ev is not None
        assert "Radarr library sync complete" in (ev.title or "")


def test_library_sync_tv_upserts_and_detects_srt(session_factory, tmp_path: Path) -> None:
    settings = MediaMopSettings.load()
    mkv = tmp_path / "ep1.mkv"
    mkv.write_bytes(b"x")
    srt = tmp_path / "ep1.en.srt"
    srt.write_text("1\n", encoding="utf-8")

    with session_factory() as s:
        s.add(_sonarr_row(settings))
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="lsync:tv:1",
            job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_TV,
            payload_json="{}",
        )
        s.commit()

    series = [{"id": 1, "title": "Show"}]
    episodes = [
        {
            "id": 100,
            "title": "Pilot",
            "seasonNumber": 1,
            "episodeNumber": 1,
            "hasFile": True,
            "episodeFile": {"path": str(mkv)},
        },
    ]

    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with (
        patch("mediamop.modules.subber.subber_library_sync_job_handler.get_sonarr_series", return_value=series),
        patch("mediamop.modules.subber.subber_library_sync_job_handler.get_sonarr_episodes", return_value=episodes),
        patch("mediamop.modules.subber.subber_library_sync_job_handler.get_sonarr_episode_files", return_value=[]),
    ):
        assert (
            process_one_subber_job(
                session_factory,
                lease_owner="ls2",
                job_handlers=handlers,
                now=t0,
                lease_seconds=600,
            )
            == "processed"
        )

    with session_factory() as s:
        rows = list(s.scalars(select(SubberSubtitleState)).all())
        assert len(rows) == 1
        r = rows[0]
        assert r.media_scope == "tv"
        assert r.status == "found"
        assert r.show_title == "Show"
        assert r.sonarr_episode_id == 100


def test_library_sync_movies_skips_without_credentials(session_factory) -> None:
    settings = MediaMopSettings.load()
    with session_factory() as s:
        s.add(SubberSettingsRow(id=1, enabled=True))
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="lsync:movies:nc",
            job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES,
            payload_json="{}",
        )
        s.commit()

    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with patch("mediamop.modules.subber.subber_library_sync_job_handler.get_radarr_movies") as m:
        assert (
            process_one_subber_job(
                session_factory,
                lease_owner="ls3",
                job_handlers=handlers,
                now=t0,
                lease_seconds=600,
            )
            == "processed"
        )
        m.assert_not_called()

    with session_factory() as s:
        assert list(s.scalars(select(SubberSubtitleState)).all()) == []
        ev = s.scalars(select(ActivityEvent).where(ActivityEvent.event_type == C.SUBBER_LIBRARY_SYNC_COMPLETED)).first()
        assert ev is not None
        assert "skipped" in (ev.title or "").lower()


def test_upsert_does_not_downgrade_found_to_missing(session_factory) -> None:
    settings = MediaMopSettings.load()
    mkv = "/virtual/movie.mkv"
    with session_factory() as s:
        s.add(_radarr_row(settings))
        s.add(
            SubberSubtitleState(
                media_scope="movies",
                file_path=mkv,
                language_code="en",
                status="found",
                subtitle_path="/old/path.en.srt",
            ),
        )
        s.commit()

    movies_payload = [
        {"id": 1, "title": "M", "year": 2020, "hasFile": True, "movieFile": {"path": mkv}},
    ]

    with session_factory() as s:
        subber_enqueue_or_get_job(
            s,
            dedupe_key="lsync:movies:nd",
            job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_MOVIES,
            payload_json="{}",
        )
        s.commit()

    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with patch("mediamop.modules.subber.subber_library_sync_job_handler.get_radarr_movies", return_value=movies_payload):
        process_one_subber_job(session_factory, lease_owner="ls4", job_handlers=handlers, now=t0, lease_seconds=600)

    with session_factory() as s:
        r = s.scalars(select(SubberSubtitleState).where(SubberSubtitleState.file_path == mkv)).one()
        assert r.status == "found"


def test_library_sync_tv_resolves_path_via_episode_file_table(session_factory, tmp_path: Path) -> None:
    """When episodeFile omits path, map from /api/v3/episodefile by episode file id."""
    settings = MediaMopSettings.load()
    mkv = tmp_path / "from-file-table.mkv"
    mkv.write_bytes(b"x")

    with session_factory() as s:
        s.add(_sonarr_row(settings))
        s.commit()
        subber_enqueue_or_get_job(
            s,
            dedupe_key="lsync:tv:ef",
            job_kind=SUBBER_JOB_KIND_LIBRARY_SYNC_TV,
            payload_json="{}",
        )
        s.commit()

    series = [{"id": 1, "title": "Show"}]
    episodes = [
        {
            "id": 200,
            "title": "A",
            "seasonNumber": 1,
            "episodeNumber": 2,
            "hasFile": True,
            "episodeFile": {"id": 555},
        },
    ]
    ep_files = [{"id": 555, "path": str(mkv), "seriesId": 1}]

    handlers = build_subber_job_handlers(settings, session_factory)
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with (
        patch("mediamop.modules.subber.subber_library_sync_job_handler.get_sonarr_series", return_value=series),
        patch("mediamop.modules.subber.subber_library_sync_job_handler.get_sonarr_episodes", return_value=episodes),
        patch("mediamop.modules.subber.subber_library_sync_job_handler.get_sonarr_episode_files", return_value=ep_files),
    ):
        process_one_subber_job(session_factory, lease_owner="ls5", job_handlers=handlers, now=t0, lease_seconds=600)

    with session_factory() as s:
        r = s.scalars(select(SubberSubtitleState).where(SubberSubtitleState.sonarr_episode_id == 200)).one()
        assert r.file_path == str(mkv)


def test_upsert_service_merge_found_over_missing(session_factory) -> None:
    with session_factory() as s:
        s.add(SubberSettingsRow(id=1, enabled=True))
        upsert_subtitle_state(
            s,
            media_scope="movies",
            file_path="/x/a.mkv",
            language_code="en",
            status="found",
            subtitle_path="/x/a.en.srt",
            source="webhook",
        )
        s.commit()
        upsert_subtitle_state(
            s,
            media_scope="movies",
            file_path="/x/a.mkv",
            language_code="en",
            status="missing",
            source="sync",
        )
        s.commit()
        r = s.scalars(select(SubberSubtitleState).where(SubberSubtitleState.file_path == "/x/a.mkv")).one()
        assert r.status == "found"
