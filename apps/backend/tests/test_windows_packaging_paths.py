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
    assert "SetupIconFile={#RepoRoot}\\packaging\\windows\\assets\\mediamop-tray-icon.ico" in text
    assert "DisableWelcomePage=no" in text
    assert "DisableDirPage=no" in text
    assert "DisableProgramGroupPage=no" in text
    assert "DisableReadyPage=no" in text
    assert "CloseApplications=no" in text
    assert "RestartApplications=no" in text
    assert "taskkill.exe" in text
    assert "advfirewall firewall add rule" in text
    assert 'program=""{app}\\MediaMopServer.exe""' in text
    assert "MediaMop.exe" in text
    assert "MediaMopServer.exe" in text


def test_windows_package_uses_dedicated_tray_icon_assets() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec = repo / "packaging" / "windows" / "mediamop-tray.spec"
    text = spec.read_text(encoding="utf-8")

    assert (repo / "packaging" / "windows" / "assets" / "mediamop-tray-icon.png").is_file()
    assert (repo / "packaging" / "windows" / "assets" / "mediamop-tray-icon.ico").is_file()
    assert 'TRAY_ICON_PNG = ROOT / "packaging" / "windows" / "assets" / "mediamop-tray-icon.png"' in text
    assert 'TRAY_ICON_ICO = ROOT / "packaging" / "windows" / "assets" / "mediamop-tray-icon.ico"' in text
    assert "(str(TRAY_ICON_PNG), \"assets\")" in text
    assert "(str(TRAY_ICON_ICO), \"assets\")" in text
    assert "(str(THIRD_PARTY_NOTICES), \".\")" in text
    assert "icon=str(TRAY_ICON_ICO)" in text


def test_windows_package_includes_ffmpeg_runtime_assets() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec = repo / "packaging" / "windows" / "mediamop-tray.spec"
    build = repo / "packaging" / "windows" / "build.ps1"
    spec_text = spec.read_text(encoding="utf-8")
    build_text = build.read_text(encoding="utf-8")

    assert 'FFMPEG_VENDOR = ROOT / "packaging" / "windows" / "vendor" / "ffmpeg"' in spec_text
    assert '(str(FFMPEG_VENDOR), "bin/ffmpeg")' in spec_text
    assert "Ensure-WindowsFfmpegRuntime" in build_text
    assert "ffmpeg-master-latest-win64-lgpl.zip" in build_text


def test_packaged_server_binds_to_lan_interfaces() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8")

    assert 'host="0.0.0.0"' in source
    assert 'host="127.0.0.1"' not in source
    assert "MediaMop LAN URLs" in source
