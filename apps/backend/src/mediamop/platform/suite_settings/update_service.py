"""Release-check logic for the Settings page."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx

from mediamop.platform.suite_settings.schemas import SuiteUpdateStatusOut
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
    windows_installer_url: str | None = None
    assets = payload.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "").strip().lower()
            if name == "mediamopsetup.exe":
                windows_installer_url = str(asset.get("browser_download_url") or "").strip() or None
                break

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
