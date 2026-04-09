"""MediaMop product path root (no database)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mediamop.core.paths import default_mediamop_home, resolve_mediamop_home


def test_resolve_explicit_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "custom-mb"
    monkeypatch.setenv("MEDIAMOP_HOME", str(target))
    assert resolve_mediamop_home() == target.resolve()


def test_default_home_leaf_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEDIAMOP_HOME", raising=False)
    home = default_mediamop_home()
    assert home.name in ("MediaMop", "mediamop")
