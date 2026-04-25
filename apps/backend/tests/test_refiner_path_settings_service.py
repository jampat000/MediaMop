"""Unit tests for Refiner path settings helpers (no shared DB mutation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow
from mediamop.modules.refiner.refiner_path_settings_service import (
    _validate_path_separation,
    effective_work_folder,
    resolved_default_refiner_tv_work_folder,
    resolved_default_refiner_work_folder,
)


def test_resolved_default_work_under_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    h = tmp_path / "home2"
    h.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(h))
    s = MediaMopSettings.load()
    got = resolved_default_refiner_work_folder(mediamop_home=s.mediamop_home)
    assert got == str(h.resolve() / "refiner" / "refiner-movie-work")
    assert Path(got).is_absolute()


def test_resolved_default_tv_work_under_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!")
    h = tmp_path / "home_tv"
    h.mkdir()
    monkeypatch.setenv("MEDIAMOP_HOME", str(h))
    s = MediaMopSettings.load()
    got = resolved_default_refiner_tv_work_folder(mediamop_home=s.mediamop_home)
    assert got == str(h.resolve() / "refiner" / "refiner-tv-work")
    assert Path(got).is_absolute()


def test_legacy_movie_default_is_treated_as_default(tmp_path: Path) -> None:
    row = RefinerPathSettingsRow(id=1, refiner_work_folder=r"C:\ProgramData\Media\refiner-movie-work")

    got, is_default = effective_work_folder(row=row, mediamop_home=str(tmp_path))

    assert is_default is True
    assert got == str(tmp_path.resolve() / "refiner" / "refiner-movie-work")


def test_validate_rejects_nested_watched_and_output(tmp_path: Path) -> None:
    w = tmp_path / "w"
    w.mkdir()
    o = w / "inside" / "out"
    o.mkdir(parents=True)
    work = tmp_path / "wk"
    work.mkdir()
    with pytest.raises(ValueError, match="watched folder and output folder"):
        _validate_path_separation(watched=w.resolve(), work=work.resolve(), output=o.resolve())


def test_validate_rejects_same_work_and_output(tmp_path: Path) -> None:
    x = tmp_path / "same"
    x.mkdir()
    with pytest.raises(ValueError, match="work/temp folder and output folder"):
        _validate_path_separation(watched=None, work=x.resolve(), output=x.resolve())
