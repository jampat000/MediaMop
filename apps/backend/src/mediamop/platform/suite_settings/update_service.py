"""Release-check logic for the Settings page.

With Velopack, delta updates are handled entirely by the .NET tray app.
The backend only checks GitHub releases for version comparison so the
Settings page can show current vs. latest.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

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
    update_available = bool(
        current_parsed and latest_parsed and latest_parsed > current_parsed
    )

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
            "Updates are managed by the MediaMop desktop app via Velopack."
            if install_type == "windows"
            else None
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
