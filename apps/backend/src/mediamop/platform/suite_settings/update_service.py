"""Release-check logic for the Settings page."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.schemas import SuiteUpdateStartOut, SuiteUpdateStatusOut
from mediamop.version import __version__
from mediamop.windows.updater_service import UPDATER_PORT

logger = logging.getLogger(__name__)

GH_REPO = "jampat000/MediaMop"
GH_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GH_REPO}/releases/latest"
DOCKER_IMAGE = "ghcr.io/jampat000/mediamop"

_WINDOWS_LEGACY_UPGRADE_SUMMARY = (
    "This Windows install does not have the MediaMop updater service yet. "
    "Remote in-app upgrade is not available until one newer installer has been run locally as administrator."
)
_WINDOWS_UPDATER_READY_SUMMARY = "Remote in-app upgrade is ready on this Windows install."


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


def _runtime_home(settings: MediaMopSettings | None = None) -> Path:
    if settings is not None:
        return Path(settings.mediamop_home)
    raw = (os.environ.get("MEDIAMOP_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    program_data = (os.environ.get("PROGRAMDATA") or r"C:\ProgramData").strip()
    return Path(program_data) / "MediaMop"


def _install_root() -> Path:
    if getattr(sys, "frozen", False) and os.name == "nt":
        resolved = Path(sys.executable).resolve().parent
        logger.debug("update_service._install_root resolved to %s (frozen)", resolved)
        return resolved
    resolved = _runtime_home()
    logger.debug("update_service._install_root resolved to %s (unfrozen)", resolved)
    return resolved


def _updater_token_path(settings: MediaMopSettings | None = None) -> Path:
    if getattr(sys, "frozen", False) and os.name == "nt":
        return _install_root() / "updater.secret"
    return _runtime_home(settings) / "updater.secret"


def _updater_token_paths(settings: MediaMopSettings | None = None) -> list[Path]:
    paths: list[Path] = []
    for candidate in (_install_root() / "updater.secret", _runtime_home(settings) / "updater.secret"):
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _read_updater_token(settings: MediaMopSettings | None = None) -> str | None:
    for path in _updater_token_paths(settings):
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if len(token) >= 32:
            return token
    return None


def _updater_base_url() -> str:
    port = int((os.environ.get("MEDIAMOP_UPDATER_PORT") or str(UPDATER_PORT)).strip())
    return f"http://127.0.0.1:{port}"


def _updater_headers(settings: MediaMopSettings | None = None) -> dict[str, str] | None:
    token = _read_updater_token(settings)
    if not token:
        return None
    return {"X-MediaMop-Updater-Token": token}


def _windows_updater_service_ready(settings: MediaMopSettings | None = None) -> bool:
    ready, _summary = _windows_updater_service_state(settings)
    return ready


def _windows_updater_service_state(settings: MediaMopSettings | None = None) -> tuple[bool, str]:
    if os.name != "nt":
        return False, _WINDOWS_LEGACY_UPGRADE_SUMMARY
    headers = _updater_headers(settings)
    if not headers:
        logger.warning(
            "MediaMop updater service token not found at %s; in-app upgrade will be unavailable. "
            "Ensure the updater service has been installed by running the MediaMop installer as administrator.",
            _updater_token_path(settings),
        )
        return False, _WINDOWS_LEGACY_UPGRADE_SUMMARY
    try:
        response = httpx.get(f"{_updater_base_url()}/api/v1/status", headers=headers, timeout=3.0)
    except Exception:
        return (
            False,
            "Remote in-app upgrade is unavailable because MediaMop could not reach the local updater service. "
            "Ensure the MediaMop Updater service is running on this computer, then click Check again.",
        )
    if response.status_code == 200:
        return True, _WINDOWS_UPDATER_READY_SUMMARY
    if response.status_code in {401, 403}:
        return (
            False,
            "Remote in-app upgrade is unavailable because the local updater service token did not match this app "
            "install. Run the latest MediaMop installer locally once as administrator to repair updater pairing.",
        )
    return (
        False,
        f"Remote in-app upgrade is unavailable because the local updater service returned HTTP {response.status_code}.",
    )


def _assert_safe_installer_url(installer_url: str) -> str:
    parsed = urlparse(installer_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        msg = "Installer download URL must use HTTPS."
        raise ValueError(msg)
    if host not in {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }:
        msg = "Installer download URL must come from GitHub Releases."
        raise ValueError(msg)
    return installer_url


def _start_windows_updater_service_apply(
    settings: MediaMopSettings,
    *,
    installer_url: str,
    target_version: str,
) -> tuple[bool, str]:
    headers = _updater_headers(settings)
    if not headers:
        return False, _WINDOWS_LEGACY_UPGRADE_SUMMARY
    try:
        response = httpx.post(
            f"{_updater_base_url()}/api/v1/apply",
            headers=headers,
            json={
                "installer_url": _assert_safe_installer_url(installer_url),
                "target_version": target_version,
            },
            timeout=10.0,
        )
    except Exception as exc:
        return False, f"MediaMop could not reach the local updater service: {exc}"
    if response.status_code != 200:
        try:
            payload = response.json()
            detail = str(payload.get("detail") or "").strip()
        except Exception:
            detail = ""
        return False, detail or "MediaMop could not start the local updater service request."
    try:
        payload = response.json()
    except Exception:
        return False, "MediaMop updater service returned an invalid response."
    return bool(payload.get("accepted")), str(payload.get("message") or "").strip()


def build_suite_update_status(settings: MediaMopSettings | None = None) -> SuiteUpdateStatusOut:
    install_type = _detect_install_type()
    current_version = __version__ or "1.0.0"
    windows_updater_ready = False
    windows_upgrade_summary: str | None = None
    if install_type == "windows":
        windows_updater_ready, windows_upgrade_summary = _windows_updater_service_state(settings)
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
                in_app_upgrade_supported=windows_updater_ready,
                in_app_upgrade_summary=windows_upgrade_summary,
            )
        return SuiteUpdateStatusOut(
            current_version=current_version,
            install_type=install_type,
            status="unavailable",
            summary="Could not check for updates right now.",
            docker_image=DOCKER_IMAGE if install_type == "docker" else None,
            in_app_upgrade_supported=windows_updater_ready,
            in_app_upgrade_summary=windows_upgrade_summary,
        )
    except Exception:
        return SuiteUpdateStatusOut(
            current_version=current_version,
            install_type=install_type,
            status="unavailable",
            summary="Could not check for updates right now.",
            docker_image=DOCKER_IMAGE if install_type == "docker" else None,
            in_app_upgrade_supported=windows_updater_ready,
            in_app_upgrade_summary=windows_upgrade_summary,
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
        in_app_upgrade_supported=windows_updater_ready,
        in_app_upgrade_summary=windows_upgrade_summary,
    )


def start_suite_update_now(settings: MediaMopSettings) -> SuiteUpdateStartOut:
    """Request an in-place upgrade from the local Windows updater service."""

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
    task_log_path = upgrade_dir / "updater-service.log"
    started, detail = _start_windows_updater_service_apply(
        settings,
        installer_url=installer_url,
        target_version=latest_version,
    )
    if started:
        return SuiteUpdateStartOut(
            status="started",
            message=(
                detail
                or "Upgrade started using the MediaMop updater service. MediaMop will close, install the update, "
                "reopen, and this page should reconnect after the app is back."
            ),
            target_version=latest_version,
            log_path=str(task_log_path),
        )
    return SuiteUpdateStartOut(
        status="unavailable",
        message=detail or _WINDOWS_LEGACY_UPGRADE_SUMMARY,
        target_version=latest_version,
        log_path=str(task_log_path),
    )
