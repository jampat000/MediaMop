from __future__ import annotations

from pathlib import Path
import re
import threading

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
    assert "MediaMopServer.exe" in text
    assert "MediaMop.exe" in text
    assert "MediaMopServer.exe" in text


def test_windows_installer_startup_task_is_explicit_and_opt_in() -> None:
    installer = Path(__file__).resolve().parents[3] / "packaging" / "windows" / "MediaMop.iss"
    text = installer.read_text(encoding="utf-8")

    assert 'Name: "startup"; Description: "Start MediaMop when Windows starts"' in text
    assert 'Flags: unchecked' in text
    assert 'Root: HKCU; Subkey: "Software\\Microsoft\\Windows\\CurrentVersion\\Run"' in text
    assert 'ValueName: "MediaMop"' in text
    assert 'ValueData: """{app}\\{#ExeName}"""' in text
    assert "uninsdeletevalue" in text
    assert "Tasks: startup" in text


def test_windows_installer_surfaces_firewall_rule_failures() -> None:
    installer = Path(__file__).resolve().parents[3] / "packaging" / "windows" / "MediaMop.iss"
    text = installer.read_text(encoding="utf-8")

    assert "procedure InstallFirewallRule()" in text
    assert "profile=private,domain" in text
    assert "procedure ShowInstallNotice" in text
    assert "SuppressibleMsgBox(" in text
    assert re.search(r"(?<!Suppressible)MsgBox\(", text) is None
    assert "TaskDialogMsgBox(" not in text
    assert "SuppressibleTaskDialogMsgBox(" not in text
    assert "WizardSilent" in text
    assert "Windows did not allow Setup to add the firewall rule" in text
    assert 'Filename: "{sys}\\netsh.exe"; Parameters: "advfirewall firewall add rule' not in text


def test_windows_installer_uses_explicit_interactive_launch_check() -> None:
    installer = Path(__file__).resolve().parents[3] / "packaging" / "windows" / "MediaMop.iss"
    text = installer.read_text(encoding="utf-8")

    assert "function ShouldLaunchMediaMopAfterInstall(): Boolean;" in text
    assert (
        'Filename: "{app}\\{#ExeName}"; Description: "Launch MediaMop"; Flags: nowait postinstall; '
        "Check: ShouldLaunchMediaMopAfterInstall"
    ) in text
    assert "skipifsilent" not in text
    assert "updater-service relaunch handles post-upgrade startup" in text


def test_windows_installer_installs_dedicated_upgrade_task() -> None:
    repo = Path(__file__).resolve().parents[3]
    installer = repo / "packaging" / "windows" / "MediaMop.iss"
    updater_service_xml = repo / "packaging" / "windows" / "MediaMopUpdaterService.xml"
    text = installer.read_text(encoding="utf-8")
    service_text = updater_service_xml.read_text(encoding="utf-8")

    assert updater_service_xml.is_file()
    assert 'Source: "{#RepoRoot}\\packaging\\windows\\MediaMopUpdaterService.xml"; DestDir: "{app}"' in text
    assert 'Source: "{#RepoRoot}\\packaging\\windows\\vendor\\winsw\\WinSW-x64.exe"; DestDir: "{app}"; DestName: "MediaMopUpdaterService.exe"; Flags: ignoreversion' in text
    assert "function UpdaterServiceInstalled(): Boolean;" in text
    assert "procedure InstallUpdaterService();" in text
    assert "procedure FailInstall" in text
    assert "MediaMopUpdaterService.exe" in text
    assert "Remote in-app upgrades depend on that service." in text
    assert 'Filename: "{sys}\\schtasks.exe"; Parameters: "/Delete /TN ""MediaMop Upgrade"" /F"' in text
    assert "<id>MediaMopUpdater</id>" in service_text
    assert "<name>MediaMop Updater</name>" in service_text
    assert "<executable>%BASE%\\MediaMopUpdater.exe</executable>" in service_text
    assert "WaitForMediaMopProcessesToExit" in text


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
    assert 'copy_metadata("mediamop-backend")' in text
    assert "icon=str(TRAY_ICON_ICO)" in text
    assert 'name="MediaMopUpdater"' in text
    assert 'str(BACKEND / "src" / "mediamop" / "windows" / "updater_service.py")' in text


def test_windows_package_includes_ffmpeg_runtime_assets() -> None:
    repo = Path(__file__).resolve().parents[3]
    spec = repo / "packaging" / "windows" / "mediamop-tray.spec"
    build = repo / "packaging" / "windows" / "build.ps1"
    spec_text = spec.read_text(encoding="utf-8")
    build_text = build.read_text(encoding="utf-8")

    assert 'FFMPEG_VENDOR = ROOT / "packaging" / "windows" / "vendor" / "ffmpeg"' in spec_text
    assert '(str(FFMPEG_VENDOR), "bin/ffmpeg")' in spec_text
    assert "Ensure-WindowsFfmpegRuntime" in build_text
    assert "autobuild-2026-04-29-13-28" in build_text
    assert "ffmpeg-N-124254-g397c7c7524-win64-lgpl.zip" in build_text
    assert "Get-FileHash" in build_text
    assert "Ensure-WindowsServiceWrapper" in build_text
    assert "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe" in build_text
    assert "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da" in build_text
    assert "MEDIAMOP_BUILD_VERSION" in build_text
    assert "$buildVersion.StartsWith(\"v\")" in build_text
    assert "does not match backend project version" in build_text
    assert "MediaMopServer.exe reports version" in build_text
    assert "expected build version" in build_text
    assert "MediaMopUpdater.exe reports version" in build_text


def test_release_workflow_generates_checksum_and_uses_normalized_semver() -> None:
    workflow = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")

    assert 'run: echo "plain=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"' in text
    assert "MEDIAMOP_BUILD_VERSION: ${{ steps.version.outputs.plain }}" in text
    assert 'scripts/smoke-windows-package.ps1 -ExpectedVersion "${{ steps.version.outputs.plain }}"' in text
    assert 'MediaMopSetup.exe.sha256' in text
    assert 'id: codesign' in text
    assert "steps.codesign.outputs.enabled == 'true'" in text
    assert "if: ${{ secrets." not in text
    assert "Get-AuthenticodeSignature" in text


def test_packaged_server_binds_to_lan_interfaces() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8")

    assert 'host="0.0.0.0"' in source
    assert 'host="127.0.0.1"' not in source
    assert "MediaMop LAN URLs" in source


def test_tray_double_click_opens_mediamop() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8")

    assert 'Item("Open MediaMop", self._handle_open, default=True)' in source
    assert 'if "--version" in sys.argv:' in source
    assert '"--no-browser" in sys.argv' in source
    assert "open_browser_on_ready=not no_browser" in source


def test_tray_open_action_debounces_duplicate_open_requests() -> None:
    assert tray_app._is_recent_browser_open(10.0, 10.8) is True
    assert tray_app._is_recent_browser_open(10.0, 11.5) is False


def test_tray_open_handler_ignores_duplicate_callbacks_within_cooldown(monkeypatch) -> None:
    app = tray_app._MediaMopTrayApp.__new__(tray_app._MediaMopTrayApp)
    app._port = 8788
    app._last_browser_open_at = 0.0
    app._browser_open_lock = threading.Lock()
    app._log = lambda _message: None
    opened_ports: list[int] = []
    monkeypatch.setattr(tray_app, "_open_browser", lambda port: opened_ports.append(port))

    app._open_browser_with_debounce(source="tray")
    app._open_browser_with_debounce(source="tray")

    assert opened_ports == [8788]


def test_tray_open_action_uses_browser_window_reuse_mode() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8")

    assert "webbrowser.open(f\"http://127.0.0.1:{port}/\", new=0)" in source


def test_tray_duplicate_launch_opens_existing_instance_browser(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir(parents=True, exist_ok=True)
    (runtime_home / "current-port.txt").write_text("8799", encoding="utf-8")
    observed: dict[str, int | None] = {"port": None}
    monkeypatch.setattr(tray_app, "_open_browser", lambda port: observed.__setitem__("port", port))

    tray_app._maybe_open_existing_instance_browser(runtime_home)

    assert observed["port"] == 8799


def test_tray_uses_single_instance_guard_for_desktop_icon() -> None:
    source = Path(tray_app.__file__).read_text(encoding="utf-8")

    assert "Local\\\\MediaMopTrayHostSingleton" in source
    assert "Tray host launch skipped: an existing MediaMop tray instance is already running." in source
