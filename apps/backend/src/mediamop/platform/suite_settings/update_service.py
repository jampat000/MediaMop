"""Release-check logic and Windows updater status mirroring for the Settings page."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

from mediamop.core.config import MediaMopSettings
from mediamop.platform.observability.diagnostics import sanitize_diagnostic_value
from mediamop.platform.suite_settings.release_catalog import (
    GH_REPO_SLUG,
    WINDOWS_INSTALLER_ASSET_NAME,
    fetch_latest_release_record,
    normalize_release_version,
    parse_version_key,
)
from mediamop.platform.suite_settings.schemas import (
    SuiteUpdateDiagnosticsOut,
    SuiteUpdateStartOut,
    SuiteUpdateStatusOut,
    SuiteUpgradeProgressOut,
)
from mediamop.version import __version__, resolve_packaged_version
from mediamop.windows.updater_service import UPDATER_PORT

logger = logging.getLogger(__name__)

DOCKER_IMAGE = "ghcr.io/jampat000/mediamop"
_WINDOWS_LEGACY_UPGRADE_SUMMARY = (
    "This Windows install does not have the MediaMop updater service yet. "
    "Remote in-app upgrade is not available until one newer installer has been run locally as administrator."
)
_WINDOWS_UPDATER_READY_SUMMARY = "Remote in-app upgrade is ready on this Windows install."
_WINDOWS_UPDATER_UNREACHABLE_SUMMARY = (
    "Remote in-app upgrade is unavailable because MediaMop could not reach the local updater service. "
    "Ensure the MediaMop Updater service is running on this computer, then click Check again."
)
_REQUIRED_WINDOWS_FILES: tuple[tuple[str, str], ...] = (
    ("MediaMop.exe", "MediaMop.exe"),
    ("MediaMopServer.exe", "MediaMopServer.exe"),
    ("MediaMopUpdater.exe", "MediaMopUpdater.exe"),
    ("MediaMopUpdaterService.exe", "MediaMopUpdaterService.exe"),
    ("MediaMopUpdaterService.xml", "MediaMopUpdaterService.xml"),
    ("web-dist", "_internal\\web-dist\\index.html"),
)


def _detect_install_type() -> str:
    runtime = (os.environ.get("MEDIAMOP_RUNTIME") or "").strip().lower()
    if runtime in {"windows", "docker", "source"}:
        return runtime
    if Path("/.dockerenv").exists():
        return "docker"
    if getattr(sys, "frozen", False) and os.name == "nt":
        return "windows"
    return "source"


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
    for candidate in (
        _install_root() / "updater.secret",
        _runtime_home(settings) / "updater.secret",
    ):
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


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_upgrade_progress(payload: dict[str, Any] | None) -> SuiteUpgradeProgressOut | None:
    if not payload:
        return None
    diagnostics = payload.get("diagnostics")
    return SuiteUpgradeProgressOut(
        phase=str(payload.get("phase") or "unknown"),
        message=str(payload.get("message") or "Updater status unavailable."),
        attempt_id=str(payload.get("attempt_id") or "").strip() or None,
        target_version=normalize_release_version(str(payload.get("target_version") or "")),
        current_version_seen=str(payload.get("current_version_seen") or "").strip() or None,
        downloaded_installer_path=str(payload.get("downloaded_installer_path") or "").strip() or None,
        installer_sha256=str(payload.get("installer_sha256") or "").strip() or None,
        expected_sha256=str(payload.get("expected_sha256") or "").strip() or None,
        installer_log_path=str(payload.get("installer_log_path") or "").strip() or None,
        service_log_path=str(payload.get("service_log_path") or "").strip() or None,
        install_root=str(payload.get("install_root") or "").strip() or None,
        runtime_home=str(payload.get("runtime_home") or "").strip() or None,
        last_started_at=payload.get("last_started_at"),
        last_updated_at=payload.get("last_updated_at"),
        last_completed_at=payload.get("last_completed_at"),
        last_error=str(payload.get("last_error") or "").strip() or None,
        diagnostics=diagnostics if isinstance(diagnostics, dict) else {},
    )


def _fetch_windows_updater_progress(
    settings: MediaMopSettings | None = None,
) -> tuple[bool, str, SuiteUpgradeProgressOut | None]:
    headers = _updater_headers(settings)
    if not headers:
        logger.warning(
            "MediaMop updater service token not found at %s; in-app upgrade will be unavailable. "
            "Ensure the updater service has been installed by running the MediaMop installer as administrator.",
            _updater_token_path(settings),
        )
        return False, _WINDOWS_LEGACY_UPGRADE_SUMMARY, None
    try:
        response = httpx.get(
            f"{_updater_base_url()}/api/v1/status",
            headers=headers,
            timeout=3.0,
        )
    except Exception as exc:
        logger.warning("MediaMop could not reach the local updater service: %s", exc)
        return False, _WINDOWS_UPDATER_UNREACHABLE_SUMMARY, None
    if response.status_code == 200:
        return True, _WINDOWS_UPDATER_READY_SUMMARY, _coerce_upgrade_progress(_safe_response_json(response))
    if response.status_code in {401, 403}:
        return (
            False,
            "Remote in-app upgrade is unavailable because the local updater service token did not match this app "
            "install. Run the latest MediaMop installer locally once as administrator to repair updater pairing.",
            None,
        )
    return (
        False,
        f"Remote in-app upgrade is unavailable because the local updater service returned HTTP {response.status_code}.",
        _coerce_upgrade_progress(_safe_response_json(response)),
    )


def _windows_updater_service_ready(settings: MediaMopSettings | None = None) -> bool:
    ready, _summary, _progress = _fetch_windows_updater_progress(settings)
    return ready


def _start_windows_updater_service_apply(
    settings: MediaMopSettings,
    *,
    target_version: str,
) -> tuple[bool, str, str | None]:
    headers = _updater_headers(settings)
    if not headers:
        return False, _WINDOWS_LEGACY_UPGRADE_SUMMARY, None
    try:
        response = httpx.post(
            f"{_updater_base_url()}/api/v1/apply",
            headers=headers,
            json={"target_version": normalize_release_version(target_version)},
            timeout=10.0,
        )
    except Exception as exc:
        return False, f"MediaMop could not reach the local updater service: {exc}", None
    payload = _safe_response_json(response)
    attempt_id = str(payload.get("attempt_id") or "").strip() or None
    if response.status_code != 200:
        detail = str(payload.get("detail") or payload.get("message") or "").strip()
        return False, detail or "MediaMop could not start the local updater service request.", attempt_id
    return bool(payload.get("accepted")), str(payload.get("message") or "").strip(), attempt_id


def _build_release_status(
    *,
    current_version: str,
    install_type: str,
    windows_updater_ready: bool,
    windows_upgrade_summary: str | None,
    upgrade_progress: SuiteUpgradeProgressOut | None,
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
                in_app_upgrade_supported=windows_updater_ready,
                in_app_upgrade_summary=windows_upgrade_summary,
                upgrade=upgrade_progress,
            )
        return SuiteUpdateStatusOut(
            current_version=current_version,
            install_type=install_type,
            status="unavailable",
            summary="Could not check for updates right now.",
            docker_image=DOCKER_IMAGE if install_type == "docker" else None,
            in_app_upgrade_supported=windows_updater_ready,
            in_app_upgrade_summary=windows_upgrade_summary,
            upgrade=upgrade_progress,
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
            upgrade=upgrade_progress,
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
        in_app_upgrade_supported=windows_updater_ready,
        in_app_upgrade_summary=windows_upgrade_summary,
        upgrade=upgrade_progress,
    )


def build_suite_update_status(
    settings: MediaMopSettings | None = None,
) -> SuiteUpdateStatusOut:
    install_type = _detect_install_type()
    current_version = __version__ or "0.0.0"
    windows_updater_ready = False
    windows_upgrade_summary: str | None = None
    upgrade_progress: SuiteUpgradeProgressOut | None = None
    if install_type == "windows":
        (
            windows_updater_ready,
            windows_upgrade_summary,
            upgrade_progress,
        ) = _fetch_windows_updater_progress(settings)
    return _build_release_status(
        current_version=current_version,
        install_type=install_type,
        windows_updater_ready=windows_updater_ready,
        windows_upgrade_summary=windows_upgrade_summary,
        upgrade_progress=upgrade_progress,
    )


def start_suite_update_now(settings: MediaMopSettings) -> SuiteUpdateStartOut:
    """Request an in-place upgrade from the local Windows updater service."""

    install_type = _detect_install_type()
    if install_type != "windows":
        return SuiteUpdateStartOut(
            status="unavailable",
            message="In-app upgrades are only available for the Windows desktop install. Docker/source installs must be updated outside the app.",
        )

    current_version = __version__ or "0.0.0"
    release = fetch_latest_release_record(user_agent_version=current_version)
    current_parsed = parse_version_key(current_version)
    latest_parsed = parse_version_key(release.version)
    if not latest_parsed or not current_parsed or latest_parsed <= current_parsed:
        return SuiteUpdateStartOut(
            status="unavailable",
            message="No newer Windows installer is available right now.",
            target_version=release.version,
            log_path=str(_runtime_home(settings) / "upgrades" / "updater-service.log"),
        )

    started, detail, attempt_id = _start_windows_updater_service_apply(
        settings,
        target_version=release.version,
    )
    log_path = str(_runtime_home(settings) / "upgrades" / "updater-service.log")
    if started:
        return SuiteUpdateStartOut(
            status="started",
            message=detail or "Upgrade request accepted. MediaMop is preparing the update.",
            attempt_id=attempt_id,
            target_version=release.version,
            log_path=log_path,
        )
    return SuiteUpdateStartOut(
        status="unavailable",
        message=detail or _WINDOWS_LEGACY_UPGRADE_SUMMARY,
        attempt_id=attempt_id,
        target_version=release.version,
        log_path=log_path,
    )


def _tail_lines(path: Path | None, *, limit: int = 20) -> list[str]:
    if path is None or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    trimmed = lines[-limit:]
    return [
        str(sanitize_diagnostic_value("log_line", line))[:1000]
        for line in trimmed
    ]


def _sha256_for_path(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _windows_file_version(path: Path) -> str | None:
    if os.name != "nt" or not path.is_file():
        return None
    script = (
        "$item = Get-Item -LiteralPath $args[0]; "
        "[string]$item.VersionInfo.FileVersion"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script, str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    value = (result.stdout or "").strip()
    return value or None


def _list_windows_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    script = (
        "$rows = Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'MediaMop*' -or $_.ExecutablePath -like '*MediaMop*' } | "
        "Select-Object Name, ProcessId, ExecutablePath, CommandLine; "
        "$rows | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return [{"error": f"Could not enumerate MediaMop processes: {exc}"}]
    raw = (result.stdout or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [{"error": "Could not parse MediaMop process inventory."}]
    rows = parsed if isinstance(parsed, list) else [parsed]
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "name": str(row.get("Name") or "").strip() or None,
                "pid": row.get("ProcessId"),
                "executable_path": str(row.get("ExecutablePath") or "").strip() or None,
                "command_line": str(
                    sanitize_diagnostic_value(
                        "command_line",
                        str(row.get("CommandLine") or "").strip(),
                    )
                )
                or None,
            }
        )
    return out


def _installed_file_diagnostics(install_root: Path) -> list[dict[str, Any]]:
    packaged_root = install_root / "_internal"
    packaged_version = resolve_packaged_version(packaged_root)
    items: list[dict[str, Any]] = []
    for label, relative in _REQUIRED_WINDOWS_FILES:
        path = install_root / relative
        items.append(
            {
                "label": label,
                "path": str(path),
                "exists": path.exists(),
                "sha256": _sha256_for_path(path) if path.is_file() else None,
                "file_version": _windows_file_version(path),
                "packaged_version": packaged_version if label == "MediaMopServer.exe" else None,
            }
        )
    return items


def build_suite_update_diagnostics(
    settings: MediaMopSettings | None = None,
) -> SuiteUpdateDiagnosticsOut:
    status = build_suite_update_status(settings)
    install_root = _install_root()
    runtime_home = _runtime_home(settings)
    installer_log_path = None
    service_log_path = None
    if status.upgrade is not None:
        installer_log_path = status.upgrade.installer_log_path
        service_log_path = status.upgrade.service_log_path
    else:
        default_upgrade_root = runtime_home / "upgrades"
        installer_log_path = str(default_upgrade_root / "installer-latest.log")
        service_log_path = str(default_upgrade_root / "updater-service.log")
    return SuiteUpdateDiagnosticsOut(
        current_version=status.current_version,
        latest_version=status.latest_version,
        install_type=status.install_type,
        install_root=str(install_root),
        runtime_home=str(runtime_home),
        updater_service_reachable=bool(status.in_app_upgrade_supported),
        updater_token_path_present=any(path.is_file() for path in _updater_token_paths(settings)),
        installer_log_path=installer_log_path,
        service_log_path=service_log_path,
        installer_log_tail=_tail_lines(Path(installer_log_path) if installer_log_path else None),
        service_log_tail=_tail_lines(Path(service_log_path) if service_log_path else None),
        running_processes=_list_windows_processes(),
        installed_files=_installed_file_diagnostics(install_root),
        upgrade=status.upgrade,
    )
