"""Release-check logic for the Settings page.

With Velopack, delta updates are handled entirely by the .NET tray app.
The backend only checks GitHub releases for version comparison so the
Settings page can show current vs. latest.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Literal

import httpx

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.release_catalog import (
    WINDOWS_INSTALLER_ASSET_NAME,
    fetch_latest_release_record,
    normalize_release_version,
    parse_version_key,
)
from mediamop.platform.suite_settings.schemas import (
    SuiteUpdateStatusOut,
    UpdateSettingsOut,
    UpdateStateOut,
)
from mediamop.version import __version__

logger = logging.getLogger(__name__)

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


def _build_release_status(
    *,
    current_version: str,
    install_type: str,
) -> SuiteUpdateStatusOut:
    try:
        release = fetch_latest_release_record(user_agent_version=current_version)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return SuiteUpdateStatusOut(
                current_version=current_version,
                install_type=install_type,
                status="not_published",
                summary="No public MediaMop release is published yet.",
                docker_image=DOCKER_IMAGE if install_type == "docker" else None,
                in_app_upgrade_supported=install_type == "windows",
            )
        return SuiteUpdateStatusOut(
            current_version=current_version,
            install_type=install_type,
            status="unavailable",
            summary="Could not check for updates right now.",
            docker_image=DOCKER_IMAGE if install_type == "docker" else None,
            in_app_upgrade_supported=install_type == "windows",
        )
    except Exception:
        return SuiteUpdateStatusOut(
            current_version=current_version,
            install_type=install_type,
            status="unavailable",
            summary="Could not check for updates right now.",
            docker_image=DOCKER_IMAGE if install_type == "docker" else None,
            in_app_upgrade_supported=install_type == "windows",
        )

    current_parsed = parse_version_key(current_version)
    latest_parsed = parse_version_key(release.version)
    update_available = bool(current_parsed and latest_parsed and latest_parsed > current_parsed)

    if not release.version:
        status = "unavailable"
        summary = "Could not read the latest release version."
    elif update_available:
        status = "update_available"
        summary = f"MediaMop {release.version} is available."
    else:
        status = "up_to_date"
        summary = f"This install is already on MediaMop {current_version}."

    installer_asset = release.asset_named(WINDOWS_INSTALLER_ASSET_NAME)
    docker_tag = release.version if release.version else None
    docker_update_command = None
    if install_type == "docker" and docker_tag:
        # `docker compose pull` and not `docker pull <image>:<tag>`. Two reasons, either of
        # which is fatal on its own: images publish as `v2.5.0` while `release.version` has
        # had its `v` stripped, so the explicit tag does not exist; and the compose file
        # documented in docs/docker.md pins `:latest`, so `compose up -d` would keep running
        # the old image even after a successful pull. `compose pull` resolves whatever the
        # operator's own compose file names, which is the only thing `compose up` will use.
        docker_update_command = "docker compose pull && docker compose up -d"

    return SuiteUpdateStatusOut(
        current_version=current_version,
        install_type=install_type,
        status=status,
        summary=summary,
        latest_version=release.version,
        latest_name=release.release_name or release.version,
        published_at=release.published_at,
        release_url=release.html_url,
        windows_installer_url=installer_asset.browser_download_url if installer_asset else None,
        docker_image=DOCKER_IMAGE if install_type == "docker" else None,
        docker_tag=docker_tag,
        docker_update_command=docker_update_command,
        in_app_upgrade_supported=install_type == "windows",
        in_app_upgrade_summary=(
            "Updates are managed by the MediaMop desktop app via Velopack." if install_type == "windows" else None
        ),
    )


def build_suite_update_status(
    settings: MediaMopSettings | None = None,
) -> SuiteUpdateStatusOut:
    install_type = _detect_install_type()
    current_version = __version__ or "0.0.0"
    return _build_release_status(
        current_version=current_version,
        install_type=install_type,
    )


_UPDATE_SETTINGS_FILE = "update-settings.json"
UpdateMode = Literal["Auto", "DownloadOnly", "NotifyOnly"]
_UPDATE_MODES: tuple[UpdateMode, ...] = ("Auto", "DownloadOnly", "NotifyOnly")
_DEFAULT_UPDATE_SETTINGS = UpdateSettingsOut(
    mode="Auto",
    check_on_startup=True,
    check_interval_minutes=60,
)
"""What a fresh install gets: nobody has chosen yet, and Auto is the shipped default."""

_UNREADABLE_UPDATE_SETTINGS = UpdateSettingsOut(
    mode="NotifyOnly",
    check_on_startup=True,
    check_interval_minutes=60,
)
"""What an unreadable file gets, which is a different situation from no file at all.

A file that exists but cannot be read means the operator chose something and we cannot
tell what. Auto is the only mode that installs an update with nobody watching, so guessing
it is the one guess that can act against an explicit choice — an operator who picked
NotifyOnly would be auto-updated by a truncated file. NotifyOnly still surfaces the update,
so the cost of guessing wrong in this direction is a prompt rather than an install.
"""


def get_update_settings(settings: MediaMopSettings) -> UpdateSettingsOut:
    path = Path(settings.mediamop_home) / _UPDATE_SETTINGS_FILE
    if not path.exists():
        return _DEFAULT_UPDATE_SETTINGS
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        mode = str(raw.get("mode", "")).strip()
        if mode not in _UPDATE_MODES:
            raise ValueError(f"unknown update mode {mode!r}")
        return UpdateSettingsOut(
            mode=mode,
            check_on_startup=bool(raw.get("checkOnStartup", True)),
            check_interval_minutes=int(raw.get("checkIntervalMinutes", 60)),
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        logger.warning(
            "Update settings at %s could not be read. Falling back to notify-only so a "
            "damaged file cannot install an update the operator did not choose.",
            path,
            exc_info=True,
        )
        return _UNREADABLE_UPDATE_SETTINGS


def put_update_settings(
    settings: MediaMopSettings,
    mode: UpdateMode,
    check_on_startup: bool,
    check_interval_minutes: int,
) -> UpdateSettingsOut:
    path = Path(settings.mediamop_home) / _UPDATE_SETTINGS_FILE
    payload = {
        "mode": mode,
        "checkOnStartup": check_on_startup,
        "checkIntervalMinutes": check_interval_minutes,
    }
    # Written whole and then renamed. `write_text` truncates first, so a crash mid-write
    # leaves the half-file that the read path above has to guess its way around; the point
    # of that fallback is to be unreachable in practice.
    #
    # The scratch name is unique per write, not `update-settings.json.tmp`. The tray writes
    # this same file when its menu changes the mode, and a shared scratch name lets one
    # writer rename the other's file into place: the web UI saves NotifyOnly, is told it
    # saved, and the file holds Auto. That is the silent change of an operator's choice
    # this whole path exists to prevent. mkstemp keeps it in the same directory so the
    # rename stays atomic.
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(json.dumps(payload, indent=2))
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return UpdateSettingsOut(
        mode=mode,
        check_on_startup=check_on_startup,
        check_interval_minutes=check_interval_minutes,
    )


_UPDATE_STATE_FILE = "update-state.json"
_APPLY_UPDATE_FLAG = "update-apply-now"


def get_update_state(settings: MediaMopSettings) -> UpdateStateOut:
    path = Path(settings.mediamop_home) / _UPDATE_STATE_FILE
    if not path.exists():
        return UpdateStateOut()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return UpdateStateOut(
            downloaded=bool(raw.get("downloaded", False)),
            pending_version=raw.get("version") or None,
        )
    except Exception:
        return UpdateStateOut()


def write_apply_update_flag(settings: MediaMopSettings) -> None:
    path = Path(settings.mediamop_home) / _APPLY_UPDATE_FLAG
    path.touch()
