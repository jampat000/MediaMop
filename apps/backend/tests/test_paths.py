"""MediaMop product path root (no database)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediamop.core.paths import default_mediamop_home, resolve_mediamop_home


def test_resolve_explicit_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "custom-mediamop"
    monkeypatch.setenv("MEDIAMOP_HOME", str(target))
    assert resolve_mediamop_home() == target.resolve()


def test_default_home_leaf_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_HOME", raising=False)
    home = default_mediamop_home()
    assert home.name in ("MediaMop", "mediamop")


def test_windows_default_home_is_machine_wide_programdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(default_mediamop_home()).replace("/", "\\") == r"C:\ProgramData\MediaMop"
