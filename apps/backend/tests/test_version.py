from __future__ import annotations

import sys

import weir.version as version_module
from weir.version import get_version


def test_get_version_prefers_highest_packaged_dist_info(tmp_path, monkeypatch):
    for version in ("1.0.7", "1.0.17", "1.0.13"):
        (tmp_path / f"weir_backend-{version}.dist-info").mkdir()

    monkeypatch.delenv("WEIR_VERSION", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert get_version() == "1.0.17"


def test_get_version_environment_override_wins(tmp_path, monkeypatch):
    (tmp_path / "weir_backend-1.0.17.dist-info").mkdir()

    monkeypatch.setenv("WEIR_VERSION", "9.9.9")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert get_version() == "9.9.9"


def test_get_version_prefers_source_tree_over_stale_editable_dist_info(tmp_path, monkeypatch):
    backend_root = tmp_path / "apps" / "backend"
    package_dir = backend_root / "src" / "weir"
    package_dir.mkdir(parents=True)
    (backend_root / "pyproject.toml").write_text('[project]\nversion = "1.0.28"\n', encoding="utf-8")

    monkeypatch.delenv("WEIR_VERSION", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(version_module, "__file__", (package_dir / "version.py").as_posix())
    monkeypatch.setattr(version_module, "version", lambda _name: "1.0.25")

    assert get_version() == "1.0.28"


def test_get_version_fallback_logs_and_returns_unknown(monkeypatch) -> None:
    monkeypatch.delenv("WEIR_VERSION", raising=False)
    monkeypatch.setattr(version_module, "_packaged_dist_info_version", lambda: None)
    monkeypatch.setattr(version_module, "_source_tree_version", lambda: None)
    warnings: list[str] = []

    def _warn(msg: str, *args) -> None:  # noqa: ANN002
        warnings.append(msg % args if args else msg)

    def _explode(_name: str) -> str:
        raise RuntimeError("metadata broken")

    monkeypatch.setattr(version_module.logger, "warning", _warn)
    monkeypatch.setattr(version_module, "version", _explode)

    resolved = get_version()

    assert resolved == "0.0.0"
    assert any("metadata broken" in message for message in warnings)
    assert any("fell back to 0.0.0" in message for message in warnings)


def test_source_tree_version_logs_when_pyproject_is_invalid(tmp_path, monkeypatch) -> None:
    backend_root = tmp_path / "apps" / "backend"
    package_dir = backend_root / "src" / "weir"
    package_dir.mkdir(parents=True)
    (backend_root / "pyproject.toml").write_text("[project]\nversion =\n", encoding="utf-8")
    warnings: list[str] = []

    def _warn(msg: str, *args) -> None:  # noqa: ANN002
        warnings.append(msg % args if args else msg)

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(version_module, "__file__", (package_dir / "version.py").as_posix())
    monkeypatch.setattr(version_module.logger, "warning", _warn)

    assert version_module._source_tree_version() is None

    assert any("source-tree version lookup failed" in message for message in warnings)
