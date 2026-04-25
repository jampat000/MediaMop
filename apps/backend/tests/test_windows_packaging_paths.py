from __future__ import annotations

from pathlib import Path

from mediamop.windows import tray_app


def test_packaged_tray_defaults_to_programdata(monkeypatch) -> None:
    monkeypatch.delenv("MEDIAMOP_HOME", raising=False)
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(tray_app._runtime_home()).replace("/", "\\") == r"C:\ProgramData\MediaMop"


def test_packaged_tray_falls_back_to_machine_programdata_path(monkeypatch) -> None:
    monkeypatch.delenv("MEDIAMOP_HOME", raising=False)
    monkeypatch.delenv("PROGRAMDATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(tray_app._runtime_home()).replace("/", "\\") == r"C:\ProgramData\MediaMop"


def test_packaged_tray_honors_explicit_mediamop_home(monkeypatch, tmp_path: Path) -> None:
    explicit = tmp_path / "custom-home"
    monkeypatch.setenv("MEDIAMOP_HOME", str(explicit))
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")

    assert tray_app._runtime_home() == explicit.resolve()


def test_inno_installer_uses_program_files_and_programdata() -> None:
    installer = Path(__file__).resolve().parents[3] / "packaging" / "windows" / "MediaMop.iss"
    text = installer.read_text(encoding="utf-8")

    assert "DefaultDirName={autopf}\\MediaMop" in text
    assert "PrivilegesRequired=admin" in text
    assert 'Name: "{commonappdata}\\MediaMop"; Permissions: users-modify' in text
    assert "{localappdata}\\MediaMop" not in text
    assert "{userdesktop}\\MediaMop" not in text
