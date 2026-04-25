from __future__ import annotations

import sys

from mediamop.version import get_version


def test_get_version_prefers_highest_packaged_dist_info(tmp_path, monkeypatch):
    for version in ("1.0.7", "1.0.17", "1.0.13"):
        (tmp_path / f"mediamop_backend-{version}.dist-info").mkdir()

    monkeypatch.delenv("MEDIAMOP_VERSION", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert get_version() == "1.0.17"


def test_get_version_environment_override_wins(tmp_path, monkeypatch):
    (tmp_path / "mediamop_backend-1.0.17.dist-info").mkdir()

    monkeypatch.setenv("MEDIAMOP_VERSION", "9.9.9")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert get_version() == "9.9.9"
