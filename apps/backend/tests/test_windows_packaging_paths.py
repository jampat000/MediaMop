from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from weir.windows import server_entry


def test_packaged_server_defaults_to_programdata(monkeypatch) -> None:
    monkeypatch.delenv("WEIR_HOME", raising=False)
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(server_entry._runtime_home()).replace("/", "\\") == r"C:\ProgramData\Weir"


def test_packaged_server_falls_back_to_machine_programdata_path(monkeypatch) -> None:
    monkeypatch.delenv("WEIR_HOME", raising=False)
    monkeypatch.delenv("PROGRAMDATA", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Example\AppData\Local")

    assert str(server_entry._runtime_home()).replace("/", "\\") == r"C:\ProgramData\Weir"


def test_packaged_server_honors_explicit_weir_home(monkeypatch, tmp_path: Path) -> None:
    explicit = tmp_path / "custom-home"
    monkeypatch.setenv("WEIR_HOME", str(explicit))
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")

    assert server_entry._runtime_home() == explicit.resolve()


def test_packaged_server_binds_to_lan_interfaces() -> None:
    source = Path(server_entry.__file__).read_text(encoding="utf-8")

    assert 'host="0.0.0.0"' in source
    assert 'host="127.0.0.1"' not in source


def test_server_spec_uses_dedicated_entry_point_and_assets() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec = repo / "packaging" / "windows" / "weir-server.spec"
    text = spec.read_text(encoding="utf-8")

    assert (repo / "packaging" / "windows" / "assets" / "weir-tray-icon.png").is_file()
    assert (repo / "packaging" / "windows" / "assets" / "weir-tray-icon.ico").is_file()
    assert 'TRAY_ICON_PNG = ROOT / "packaging" / "windows" / "assets" / "weir-tray-icon.png"' in text
    assert 'TRAY_ICON_ICO = ROOT / "packaging" / "windows" / "assets" / "weir-tray-icon.ico"' in text
    assert '(str(THIRD_PARTY_NOTICES), ".")' in text
    assert 'copy_metadata("weir-backend")' in text
    assert "icon=str(TRAY_ICON_ICO)" in text
    assert 'name="WeirServer"' in text
    assert 'str(BACKEND / "src" / "weir" / "windows" / "server_entry.py")' in text


def test_velopack_build_script_includes_ffmpeg_and_version_validation() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec = repo / "packaging" / "windows" / "weir-server.spec"
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
    assert "WEIR_BUILD_VERSION" in build_text
    assert '$buildVersion.StartsWith("v")' in build_text
    assert "does not match backend project version" in build_text
    assert "WeirServer.exe reports version" in build_text
    assert 'Where-Object { $_.Name -ne "tray-publish" }' in build_text
    assert "-SkipDotnetPublish requires an existing tray publish output" in build_text
    assert "New-Item -ItemType Directory -Path $distRoot -Force" in build_text
    assert 'Where-Object { $_.Include -eq "Velopack" }' in build_text
    assert '@("tool", "update", "-g", "vpk", "--version", $velopackCliVersion)' in build_text
    assert "vpk" in build_text


def test_release_workflow_uses_velopack_and_normalized_semver() -> None:
    repo = Path(__file__).resolve().parents[3]
    workflow = repo / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")
    ci_text = (repo / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    tray_project = ElementTree.parse(repo / "apps" / "tray" / "Weir.Tray" / "Weir.Tray.csproj")
    velopack_version = next(
        reference.attrib["Version"]
        for reference in tray_project.findall(".//PackageReference")
        if reference.attrib.get("Include") == "Velopack"
    )

    assert 'run: echo "plain=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"' in text
    assert "WEIR_BUILD_VERSION: ${{ steps.version.outputs.plain }}" in text
    assert 'scripts/smoke-windows-package.ps1 -ExpectedVersion "${{ steps.version.outputs.plain }}"' in text
    assert "SHA256SUMS.txt" in text
    assert "id: codesign" in text
    assert "steps.codesign.outputs.enabled == 'true'" in text
    assert "if: ${{ secrets." not in text
    assert "Get-AuthenticodeSignature" in text
    assert "build-velopack.ps1" in text
    assert "weir-windows-velopack" in text
    pinned_vpk_install = f"dotnet tool install -g vpk --version {velopack_version}"
    assert pinned_vpk_install in text
    assert pinned_vpk_install in ci_text
    assert text.count('Get-Item -LiteralPath "dist/windows/releases/Weir-win-Setup.exe" -ErrorAction Stop') == 2
    assert "Weir-*-win-Setup.exe" not in text
