"""Weir product path root (no database)."""

from __future__ import annotations

from pathlib import Path

import pytest

from weir.core.paths import default_weir_home, resolve_weir_home


def test_resolve_explicit_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "custom-weir"
    monkeypatch.setenv("WEIR_HOME", str(target))
    assert resolve_weir_home() == target.resolve()


def test_default_home_leaf_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEIR_HOME", raising=False)
    home = default_weir_home()
    assert home.name in ("Weir", "weir")


def test_windows_default_home_is_machine_wide_programdata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEIR_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(default_weir_home()).replace("/", "\\") == r"C:\ProgramData\Weir"
