"""Release-check logic for the Settings page."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.schemas import SuiteUpdateStartOut, SuiteUpdateStatusOut
from mediamop.version import __version__

GH_REPO = "jampat000/MediaMop"
GH_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GH_REPO}/releases/latest"
DOCKER_IMAGE = "ghcr.io/jampat000/mediamop"


def _detect_install_type() -> str:
    runtime = (os.environ.get("MEDIAMOP_RUNTIME") or "").strip().lower()
    if runtime in {"windows", "docker", "source"}:
        return runtime
    if Path("/.dockerenv").exists():
        return "docker"
    if getattr(sys, "frozen", False) and os.name == "nt":
        return "windows"
    return "source"


def _parse_version(raw: str | None) -> tuple[int, ...] | None:
    if not raw:
        return None
    text = raw.strip().lower().removeprefix("v")
    if not text:
        return None
    parts: list[int] = []
    for piece in text.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits == "":
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def _fetch_latest_release_payload() -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"MediaMop/{__version__}",
    }
    with httpx.Client(timeout=5.0, headers=headers, follow_redirects=True) as client:
        response = client.get(GH_RELEASES_LATEST_URL)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            msg = "Release API returned an unexpected response."
            raise ValueError(msg)
        return payload


def _find_windows_installer_asset(payload: dict[str, Any]) -> str | None:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").strip().lower()
        if name == "mediamopsetup.exe":
            return str(asset.get("browser_download_url") or "").strip() or None
    return None


def build_suite_update_status() -> SuiteUpdateStatusOut:
    install_type = _detect_install_type()
    current_version = __version__ or "1.0.0"
    try:
        payload = _fetch_latest_release_payload()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return SuiteUpdateStatusOut(
                current_version=current_version,
                install_type=install_type,
                status="not_published",
                summary="No public MediaMop release is published yet.",
                docker_image=DOCKER_IMAGE if install_type == "docker" else None,
            )
        return SuiteUpdateStatusOut(
            current_version=current_version,
            install_type=install_type,
            status="unavailable",
            summary="Could not check for updates right now.",
            docker_image=DOCKER_IMAGE if install_type == "docker" else None,
        )
    except Exception:
        return SuiteUpdateStatusOut(
            current_version=current_version,
            install_type=install_type,
            status="unavailable",
            summary="Could not check for updates right now.",
            docker_image=DOCKER_IMAGE if install_type == "docker" else None,
        )

    tag_name = str(payload.get("tag_name") or "").strip()
    latest_version = tag_name.removeprefix("v") or None
    latest_name = str(payload.get("name") or "").strip() or latest_version
    release_url = str(payload.get("html_url") or "").strip() or None
    published_at = payload.get("published_at")
    windows_installer_url = _find_windows_installer_asset(payload)

    current_parsed = _parse_version(current_version)
    latest_parsed = _parse_version(latest_version)
    update_available = bool(current_parsed and latest_parsed and latest_parsed > current_parsed)

    if latest_version is None:
        status = "unavailable"
        summary = "Could not read the latest release version."
    elif update_available:
        status = "update_available"
        summary = f"MediaMop {latest_version} is available."
    else:
        status = "up_to_date"
        summary = f"This install is already on MediaMop {current_version}."

    docker_tag = latest_version if latest_version else None
    docker_update_command = None
    if install_type == "docker" and docker_tag:
        docker_update_command = "docker compose pull && docker compose up -d"

    return SuiteUpdateStatusOut(
        current_version=current_version,
        install_type=install_type,
        status=status,
        summary=summary,
        latest_version=latest_version,
        latest_name=latest_name,
        published_at=published_at,
        release_url=release_url,
        windows_installer_url=windows_installer_url,
        docker_image=DOCKER_IMAGE if install_type == "docker" else None,
        docker_tag=docker_tag,
        docker_update_command=docker_update_command,
    )


def _write_windows_upgrade_script(*, installer_path: Path, executable_dir: Path, script_path: Path) -> None:
    log_path = installer_path.parent / "upgrade-run.log"
    exe_path = executable_dir / "MediaMop.exe"
    script = f"""$ErrorActionPreference = "Continue"
$logPath = {str(log_path)!r}
function Write-UpgradeLog([string]$message) {{
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -LiteralPath $logPath -Value "[$stamp] $message"
}}
Write-UpgradeLog "Starting MediaMop in-app upgrade."
$installer = {str(installer_path)!r}
$args = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS")
Write-UpgradeLog "Starting elevated installer. Windows may ask for permission."
$proc = Start-Process -FilePath $installer -ArgumentList $args -Verb RunAs -Wait -PassThru -ErrorAction Stop
Write-UpgradeLog "Elevated installer exited with code $($proc.ExitCode)."
$exe = {str(exe_path)!r}
if (Test-Path -LiteralPath $exe) {{
  Start-Process -FilePath $exe -WorkingDirectory {str(executable_dir)!r}
  Write-UpgradeLog "Restarted MediaMop."
}} else {{
  Write-UpgradeLog "MediaMop executable was not found after upgrade: $exe"
}}
"""
    script_path.write_text(script, encoding="utf-8")


def _launch_windows_upgrade_script(script_path: Path) -> None:
    log_path = script_path.parent / "upgrade-launch.log"
    log_path.write_text("Launching MediaMop in-app upgrade script.\n", encoding="utf-8")
    powershell = (
        Path(os.environ.get("SystemRoot") or r"C:\Windows")
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    command = str(powershell) if powershell.is_file() else "powershell.exe"
    subprocess.Popen(
        [
            command,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script_path),
        ],
        cwd=str(script_path.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
        close_fds=True,
    )


def start_suite_update_now(settings: MediaMopSettings) -> SuiteUpdateStartOut:
    """Stage and launch an in-place upgrade for packaged Windows installs."""

    install_type = _detect_install_type()
    if install_type != "windows":
        return SuiteUpdateStartOut(
            status="unavailable",
            message="In-app upgrades are only available for the Windows desktop install. Docker/source installs must be updated outside the app.",
        )

    payload = _fetch_latest_release_payload()
    latest_version = str(payload.get("tag_name") or "").strip().removeprefix("v") or None
    installer_url = _find_windows_installer_asset(payload)
    current_parsed = _parse_version(__version__)
    latest_parsed = _parse_version(latest_version)
    if not installer_url or not current_parsed or not latest_parsed or latest_parsed <= current_parsed:
        return SuiteUpdateStartOut(
            status="unavailable",
            message="No newer Windows installer is available right now.",
            target_version=latest_version,
        )

    upgrade_dir = Path(settings.mediamop_home) / "upgrades"
    upgrade_dir.mkdir(parents=True, exist_ok=True)
    installer_path = upgrade_dir / f"MediaMopSetup-{latest_version}.exe"
    with httpx.stream("GET", installer_url, timeout=60.0, follow_redirects=True) as response:
        response.raise_for_status()
        with installer_path.open("wb") as handle:
            for chunk in response.iter_bytes():
                if chunk:
                    handle.write(chunk)

    executable_dir = Path(sys.executable).resolve().parent
    script_path = upgrade_dir / "run-windows-upgrade.ps1"
    _write_windows_upgrade_script(
        installer_path=installer_path,
        executable_dir=executable_dir,
        script_path=script_path,
    )
    _launch_windows_upgrade_script(script_path)
    return SuiteUpdateStartOut(
        status="started",
        message="Upgrade started. MediaMop will close, install the update, reopen, and this page should reconnect after the app is back.",
        target_version=latest_version,
    )
