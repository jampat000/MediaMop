from __future__ import annotations

from pathlib import Path

from mediamop.windows import server_entry


def test_packaged_server_defaults_to_programdata(monkeypatch) -> None:
    monkeypatch.delenv("MEDIAMOP_HOME", raising=False)
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(server_entry._runtime_home()).replace("/", "\\") == r"C:\ProgramData\MediaMop"


def test_packaged_server_falls_back_to_machine_programdata_path(monkeypatch) -> None:
    monkeypatch.delenv("MEDIAMOP_HOME", raising=False)
    monkeypatch.delenv("PROGRAMDATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(server_entry._runtime_home()).replace("/", "\\") == r"C:\ProgramData\MediaMop"


def test_packaged_server_honors_explicit_mediamop_home(monkeypatch, tmp_path: Path) -> None:
    explicit = tmp_path / "custom-home"
    monkeypatch.setenv("MEDIAMOP_HOME", str(explicit))
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")

    assert server_entry._runtime_home() == explicit.resolve()


def test_packaged_server_binds_to_lan_interfaces() -> None:
    source = Path(server_entry.__file__).read_text(encoding="utf-8")

    assert 'host="0.0.0.0"' in source
    assert 'host="127.0.0.1"' not in source


def test_server_spec_uses_dedicated_entry_point_and_assets() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec = repo / "packaging" / "windows" / "mediamop-server.spec"
    text = spec.read_text(encoding="utf-8")

    assert (repo / "packaging" / "windows" / "assets" / "mediamop-tray-icon.png").is_file()
    assert (repo / "packaging" / "windows" / "assets" / "mediamop-tray-icon.ico").is_file()
    assert 'TRAY_ICON_PNG = ROOT / "packaging" / "windows" / "assets" / "mediamop-tray-icon.png"' in text
    assert 'TRAY_ICON_ICO = ROOT / "packaging" / "windows" / "assets" / "mediamop-tray-icon.ico"' in text
    assert '(str(THIRD_PARTY_NOTICES), ".")' in text
    assert 'copy_metadata("mediamop-backend")' in text
    assert "icon=str(TRAY_ICON_ICO)" in text
    assert 'name="MediaMopServer"' in text
    assert 'str(BACKEND / "src" / "mediamop" / "windows" / "server_entry.py")' in text


def test_velopack_build_script_includes_ffmpeg_and_version_validation() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec = repo / "packaging" / "windows" / "mediamop-server.spec"
    build = repo / "packaging" / "windows" / "build-velopack.ps1"
    spec_text = spec.read_text(encoding="utf-8")
    build_text = build.read_text(encoding="utf-8")

    assert 'FFMPEG_VENDOR = ROOT / "packaging" / "windows" / "vendor" / "ffmpeg"' in spec_text
    assert '(str(FFMPEG_VENDOR), "bin/ffmpeg")' in spec_text
    assert "Ensure-WindowsFfmpegRuntime" in build_text
    assert "ffmpeg-master-latest-win64-lgpl.zip" in build_text
    assert "checksums.sha256" in build_text
    assert "FFmpeg checksum entry" in build_text
    assert "Get-FileHash" in build_text
    assert "MEDIAMOP_BUILD_VERSION" in build_text
    assert '$buildVersion.StartsWith("v")' in build_text
    assert "does not match backend project version" in build_text
    assert "MediaMopServer.exe reports version" in build_text
    assert "vpk" in build_text


def test_release_workflow_uses_velopack_and_normalized_semver() -> None:
    workflow = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")

    assert 'run: echo "plain=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"' in text
    assert "MEDIAMOP_BUILD_VERSION: ${{ steps.version.outputs.plain }}" in text
    assert 'scripts/smoke-windows-package.ps1 -ExpectedVersion "${{ steps.version.outputs.plain }}"' in text
    assert "SHA256SUMS.txt" in text
    assert "id: codesign" in text
    assert "steps.codesign.outputs.enabled == 'true'" in text
    assert "if: ${{ secrets." not in text
    assert "Get-AuthenticodeSignature" in text
    assert "build-velopack.ps1" in text
    assert "mediamop-windows-velopack" in text
    assert "dotnet tool install -g vpk" in text
    assert "MediaMop-*-win-Setup.exe" in text
