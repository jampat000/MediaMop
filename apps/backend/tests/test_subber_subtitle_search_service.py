"""Unit tests for Subber subtitle search helpers."""

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.subber.subber_settings_model import SubberSettingsRow
from mediamop.modules.subber.subber_subtitle_search_service import (
    MAX_SRT_BYTES,
    _extract_srt_from_zip_or_raw,
    _write_srt_for_state,
    apply_path_mapping,
)
from mediamop.modules.subber.subber_subtitle_state_model import SubberSubtitleState
from mediamop.platform.file_lifecycle.guardrails import DiskSpaceCheck


def test_apply_path_mapping_noop_when_disabled() -> None:
    assert apply_path_mapping("/mnt/x/a.mkv", "/arr/", "/sub/", False) == "/mnt/x/a.mkv"


def test_apply_path_mapping_replaces_prefix() -> None:
    assert apply_path_mapping("/arr/show/a.mkv", "/arr", "/mnt/nas", True) == "/mnt/nas/show/a.mkv"


def test_apply_path_mapping_empty_arr_path() -> None:
    assert apply_path_mapping("/arr/a.mkv", "", "/x", True) == "/arr/a.mkv"


def test_subber_write_preflights_target_disk_space(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    movie = tmp_path / "movie.mkv"
    movie.write_bytes(b"media")

    monkeypatch.setattr(
        "mediamop.modules.subber.subber_subtitle_search_service.check_minimum_free_disk_space",
        lambda *, target_path, required_mb: DiskSpaceCheck(
            ok=False,
            checked_path=Path(target_path).parent,
            free_mb=100.0,
            required_mb=required_mb,
            message="Skipped: insufficient disk space on target drive (0.1 GB < 5.0 GB required).",
        ),
    )

    with fac() as db:
        settings_row = db.get(SubberSettingsRow, 1)
        if settings_row is None:
            settings_row = SubberSettingsRow(id=1)
            db.add(settings_row)
        state = SubberSubtitleState(
            media_scope="movie",
            file_path=str(movie),
            language_code="en",
            status="missing",
        )
        db.add(state)
        guardrail = ensure_refiner_operator_settings_row(db)
        guardrail.minimum_free_disk_space_mb = 5120
        db.flush()

        with pytest.raises(RuntimeError, match="insufficient disk space"):
            _write_srt_for_state(
                settings_row=settings_row,
                state_row=state,
                lang="en",
                srt_bytes=b"1\n00:00:00,000 --> 00:00:01,000\nHi\n",
                provider_key="provider",
                external_file_id="123",
                db=db,
            )

    assert not (tmp_path / "movie.en.srt").exists()


def test_subber_write_uses_atomic_replace(tmp_path: Path) -> None:
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    movie = tmp_path / "movie.mkv"
    movie.write_bytes(b"media")

    with fac() as db:
        settings_row = db.get(SubberSettingsRow, 1)
        if settings_row is None:
            settings_row = SubberSettingsRow(id=1)
            db.add(settings_row)
        state = SubberSubtitleState(
            media_scope="movie",
            file_path=str(movie),
            language_code="en",
            status="missing",
        )
        db.add(state)
        db.flush()

        _write_srt_for_state(
            settings_row=settings_row,
            state_row=state,
            lang="en",
            srt_bytes=b"1\n00:00:00,000 --> 00:00:01,000\nHi\n",
            provider_key="provider",
            external_file_id="123",
            db=db,
        )

    assert (tmp_path / "movie.en.srt").read_text(encoding="utf-8").startswith("1\n")
    assert not (tmp_path / "movie.en.srt.tmp").exists()


def test_extract_srt_from_zip_skips_oversized_members(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeZipFile:
        def __enter__(self) -> _FakeZipFile:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def namelist(self) -> list[str]:
            return ["huge.srt", "ok.srt"]

        def getinfo(self, name: str) -> SimpleNamespace:
            if name == "huge.srt":
                return SimpleNamespace(file_size=MAX_SRT_BYTES + 1)
            return SimpleNamespace(file_size=32)

        def read(self, name: str) -> bytes:
            if name == "ok.srt":
                return b"1\n00:00:00,000 --> 00:00:01,000\nHi\n"
            return b"small"

    monkeypatch.setattr(zipfile, "is_zipfile", lambda _: True)
    monkeypatch.setattr(zipfile, "ZipFile", lambda _: _FakeZipFile())
    out = _extract_srt_from_zip_or_raw(b"archive")

    assert out.startswith(b"1\n00:00:00,000")
