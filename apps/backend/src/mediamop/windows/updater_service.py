"""Dedicated local Windows updater service for MediaMop in-app upgrades."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path, PosixPath, WindowsPath
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from mediamop.platform.suite_settings.release_catalog import (
    GH_REPO_SLUG,
    WINDOWS_INSTALLER_ASSET_NAME,
    WINDOWS_INSTALLER_SHA256_ASSET_NAME,
    fetch_release_record_by_version,
    normalize_release_version,
)
from mediamop.version import __version__, resolve_packaged_version

UPDATER_PORT = 8791
_STATE_LOCK = threading.Lock()
_APPLY_LOCK = threading.Lock()
_RECONCILE_LOCK = threading.Lock()
_ACTIVE_PHASES = {
    "checking",
    "downloading",
    "verifying_download",
    "installer_started",
    "installer_running",
    "restarting",
    "verifying_install",
}
_RECOVERABLE_PHASES = {"installer_started", "installer_running", "restarting", "verifying_install"}
_INSTALLER_WAIT_TIMEOUT_SECONDS = 90 * 60
_VERIFY_INSTALL_TIMEOUT_SECONDS = 5 * 60
_STALE_ATTEMPT_SECONDS = 30 * 60
_BACKEND_POLL_INTERVAL_SECONDS = 2.0
_MIN_INSTALLER_BYTES = 512 * 1024
_SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")
_TRUSTED_RELEASE_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


def _append_service_log(message: str) -> None:
    path = _service_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def _host_path(raw: str | os.PathLike[str]) -> Path:
    path_cls = WindowsPath if sys.platform == "win32" else PosixPath
    return path_cls(os.fspath(raw))


def _runtime_home() -> Path:
    raw = (os.environ.get("MEDIAMOP_HOME") or "").strip()
    if raw:
        return _host_path(raw).expanduser().resolve()
    program_data = (os.environ.get("PROGRAMDATA") or r"C:\ProgramData").strip()
    return _host_path(program_data) / "MediaMop"


def _install_root() -> Path:
    if getattr(sys, "frozen", False) and os.name == "nt":
        resolved = _host_path(sys.executable).resolve().parent
        _append_service_log(f"updater_service._install_root resolved to {resolved} (frozen)")
        return resolved
    resolved = _runtime_home()
    _append_service_log(f"updater_service._install_root resolved to {resolved} (unfrozen)")
    return resolved


def _upgrade_root() -> Path:
    return _runtime_home() / "upgrades"


def _token_path() -> Path:
    return _install_root() / "updater.secret"


def _state_path() -> Path:
    return _upgrade_root() / "updater-state.json"


def _installer_log_path(attempt_id: str) -> Path:
    return _upgrade_root() / f"installer-{attempt_id}.log"


def _latest_installer_log_path() -> Path:
    return _upgrade_root() / "installer-latest.log"


def _service_log_path() -> Path:
    return _upgrade_root() / "updater-service.log"


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_iso(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _state_timestamp(state: dict[str, object]) -> datetime | None:
    return _parse_iso(state.get("last_updated_at")) or _parse_iso(state.get("last_started_at"))


def _state_age_seconds(state: dict[str, object]) -> float | None:
    stamp = _state_timestamp(state)
    if stamp is None:
        return None
    return max(0.0, (datetime.now(UTC) - stamp).total_seconds())


def _bool_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _pid_is_running(pid: object) -> bool:
    try:
        numeric = int(pid)
    except (TypeError, ValueError):
        return False
    if numeric <= 0:
        return False
    try:
        os.kill(numeric, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _running_media_processes() -> list[dict[str, object]]:
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
            timeout=15,
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
    out: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "name": str(row.get("Name") or "").strip() or None,
                "pid": row.get("ProcessId"),
                "executable_path": str(row.get("ExecutablePath") or "").strip() or None,
                "command_line": str(row.get("CommandLine") or "").strip() or None,
            }
        )
    return out


def _default_state() -> dict[str, object]:
    return {
        "phase": "idle",
        "message": "Updater ready.",
        "attempt_id": None,
        "target_version": None,
        "current_version_seen": __version__,
        "downloaded_installer_path": None,
        "installer_sha256": None,
        "expected_sha256": None,
        "installer_log_path": str(_latest_installer_log_path()),
        "service_log_path": str(_service_log_path()),
        "install_root": str(_install_root()),
        "runtime_home": str(_runtime_home()),
        "last_started_at": None,
        "last_updated_at": None,
        "last_completed_at": None,
        "last_error": None,
        "diagnostics": {},
    }


def _read_state_unlocked() -> dict[str, object]:
    path = _state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _default_state()
    except OSError as exc:
        _append_service_log(f"Updater state read failed at {path}: {exc}")
        return {
            **_default_state(),
            "phase": "state_corrupt",
            "message": "Updater state file is unreadable.",
            "last_error": f"Could not read updater state file: {exc}",
            "last_completed_at": _iso_now(),
        }
    except json.JSONDecodeError as exc:
        _append_service_log(f"Updater state parse failed at {path}: {exc}")
        return {
            **_default_state(),
            "phase": "state_corrupt",
            "message": "Updater state file is unreadable.",
            "last_error": f"Could not parse updater state file: {exc}",
            "last_completed_at": _iso_now(),
        }
    if not isinstance(raw, dict):
        _append_service_log(f"Updater state parse failed at {path}: expected JSON object.")
        return {
            **_default_state(),
            "phase": "state_corrupt",
            "message": "Updater state file is unreadable.",
            "last_error": "Could not parse updater state file: expected a JSON object.",
            "last_completed_at": _iso_now(),
        }
    diagnostics = raw.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raw["diagnostics"] = {}
    state = {**_default_state(), **raw}
    state["service_log_path"] = str(_service_log_path())
    state["install_root"] = str(_install_root())
    state["runtime_home"] = str(_runtime_home())
    return state


def _read_state() -> dict[str, object]:
    with _STATE_LOCK:
        return _read_state_unlocked()


def _persist_state(state: dict[str, object]) -> dict[str, object]:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["service_log_path"] = str(_service_log_path())
    state["install_root"] = str(_install_root())
    state["runtime_home"] = str(_runtime_home())
    state["last_updated_at"] = _iso_now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return state


def _write_state(**updates: object) -> dict[str, object]:
    with _STATE_LOCK:
        state = _read_state_unlocked()
        diagnostics_update = updates.pop("diagnostics", None)
        if diagnostics_update is not None:
            merged = dict(state.get("diagnostics") if isinstance(state.get("diagnostics"), dict) else {})
            if isinstance(diagnostics_update, dict):
                merged.update(diagnostics_update)
            else:
                merged = {}
            state["diagnostics"] = merged
        state.update(updates)
        return _persist_state(state)


def _transition_state(phase: str, message: str, **updates: object) -> dict[str, object]:
    previous_phase = str(_read_state().get("phase") or "unknown")
    _append_service_log(f"Transition {previous_phase} -> {phase}: {message}")
    return _write_state(phase=phase, message=message, **updates)


def _fresh_attempt_state(target_version: str, attempt_id: str) -> dict[str, object]:
    installer_log_path = _installer_log_path(attempt_id)
    state = _default_state()
    state.update(
        {
            "phase": "checking",
            "message": "Upgrade request accepted. MediaMop is checking release metadata.",
            "attempt_id": attempt_id,
            "target_version": target_version,
            "current_version_seen": __version__,
            "downloaded_installer_path": None,
            "installer_sha256": None,
            "expected_sha256": None,
            "installer_log_path": str(installer_log_path),
            "last_started_at": _iso_now(),
            "last_completed_at": None,
            "last_error": None,
            "diagnostics": {
                "helper_pid": None,
                "installer_pid": None,
                "restarted_server_pid": None,
                "release_tag": f"v{target_version}",
            },
        }
    )
    return state


def _stable_or_active_attempt_exists(state: dict[str, object]) -> bool:
    phase = str(state.get("phase") or "").strip().lower()
    if phase not in _ACTIVE_PHASES:
        return False
    attempt_id = str(state.get("attempt_id") or "").strip()
    diagnostics = state.get("diagnostics") if isinstance(state.get("diagnostics"), dict) else {}
    helper_pid = diagnostics.get("helper_pid") if isinstance(diagnostics, dict) else None
    installer_pid = diagnostics.get("installer_pid") if isinstance(diagnostics, dict) else None
    if _pid_is_running(helper_pid) or _pid_is_running(installer_pid):
        return True
    age = _state_age_seconds(state)
    if age is None:
        return bool(attempt_id)
    return age < _STALE_ATTEMPT_SECONDS


def _mark_failed(
    *,
    message: str,
    last_error: str,
    target_version: str | None = None,
    current_version_seen: str | None = None,
    diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    _append_service_log(f"Upgrade failed: {last_error}")
    return _transition_state(
        "failed",
        message,
        target_version=target_version,
        current_version_seen=current_version_seen,
        last_completed_at=_iso_now(),
        last_error=last_error,
        diagnostics=diagnostics or {},
    )


def _harden_token_acl_windows(path: Path) -> None:
    principals = ["SYSTEM", "Administrators", "INTERACTIVE"]
    cmd = ["icacls", str(path), "/inheritance:r"]
    for principal in principals:
        cmd.extend(["/grant:r", f"{principal}:R"])
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        _append_service_log(
            "Could not tighten updater.secret ACLs: "
            f"rc={result.returncode} stdout={result.stdout.strip()} stderr={result.stderr.strip()}"
        )


def _write_private_token(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path.write_text(value, encoding="utf-8")
        _harden_token_acl_windows(path)
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
    finally:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _load_or_create_token() -> str:
    path = _token_path()
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if len(token) >= 32:
        if os.name == "nt":
            _harden_token_acl_windows(path)
        return token
    token = secrets.token_urlsafe(48)
    _write_private_token(path, token)
    return token


def _validated_asset_download_url(url: str, *, version: str, asset_name: str) -> str:
    normalized = normalize_release_version(version)
    if not normalized:
        raise ValueError("Release version is missing.")
    parsed = urlparse(url)
    expected_path = f"/{GH_REPO_SLUG}/releases/download/v{normalized}/{asset_name}"
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError(f"Release asset URL for {asset_name} was not a trusted GitHub Releases URL.")
    if parsed.path != expected_path:
        raise ValueError(
            f"Release asset URL for {asset_name} did not match {GH_REPO_SLUG} tag v{normalized}."
        )
    if parsed.query or parsed.fragment:
        raise ValueError(f"Release asset URL for {asset_name} included unexpected query or fragment data.")
    return url


def _release_download_headers() -> dict[str, str]:
    return {
        "Accept": "application/octet-stream",
        "User-Agent": f"MediaMopUpdater/{__version__}",
    }


def _download_text(url: str) -> str:
    with httpx.Client(
        timeout=60.0,
        follow_redirects=False,
        headers=_release_download_headers(),
    ) as client:
        current_url = url
        for _ in range(6):
            response = client.get(current_url)
            if response.status_code in _REDIRECT_STATUS_CODES:
                location = response.headers.get("location")
                response.close()
                current_url = _validated_redirect_target(current_url, location)
                continue
            response.raise_for_status()
            return response.text
    raise ValueError("Release asset download redirected too many times.")


def _parse_sha256_manifest(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if WINDOWS_INSTALLER_ASSET_NAME.lower() in stripped.lower():
            match = _SHA256_RE.search(line)
            if match:
                return match.group(1).lower()
    stripped_text = text.strip()
    return stripped_text.lower() if _SHA256_RE.fullmatch(stripped_text) else None


def _validated_redirect_target(current_url: str, location: str | None) -> str:
    if not location:
        raise ValueError("Release asset download redirect was missing a location header.")
    resolved = urljoin(current_url, location)
    parsed = urlparse(resolved)
    if parsed.scheme != "https":
        raise ValueError("Release asset download redirected to a non-HTTPS URL.")
    if parsed.netloc.lower() not in _TRUSTED_RELEASE_DOWNLOAD_HOSTS:
        raise ValueError(
            f"Release asset download redirected to an untrusted host: {parsed.netloc}."
        )
    return resolved


def _open_trusted_download_stream(url: str) -> tuple[httpx.Client, httpx.Response]:
    client = httpx.Client(
        timeout=600.0,
        follow_redirects=False,
        headers=_release_download_headers(),
    )
    current_url = url
    try:
        for _ in range(6):
            response = client.send(client.build_request("GET", current_url), stream=True)
            if response.status_code in _REDIRECT_STATUS_CODES:
                location = response.headers.get("location")
                response.close()
                current_url = _validated_redirect_target(current_url, location)
                continue
            response.raise_for_status()
            return client, response
    except Exception:
        client.close()
        raise
    client.close()
    raise ValueError("Release asset download redirected too many times.")


def _download_installer(url: str, *, target_version: str, attempt_id: str) -> Path:
    target = _upgrade_root() / f"MediaMopSetup-{target_version}-{attempt_id}.exe"
    tmp = target.with_suffix(".download")
    total = 0
    client, response = _open_trusted_download_stream(url)
    try:
        with response:
            tmp.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    handle.write(chunk)
                    total += len(chunk)
    finally:
        client.close()
    if total < _MIN_INSTALLER_BYTES:
        tmp.unlink(missing_ok=True)
        raise ValueError("Downloaded installer is too small to be valid.")
    tmp.replace(target)
    return target


def _sha256_for_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_authenticode_signature(path: Path) -> tuple[bool, str]:
    if not _bool_env("MEDIAMOP_UPDATER_REQUIRE_AUTHENTICODE"):
        return True, "Authenticode verification not required."
    script = (
        "$signature = Get-AuthenticodeSignature -FilePath $args[0]; "
        "$out = @{ Status = [string]$signature.Status; "
        "StatusMessage = [string]$signature.StatusMessage; "
        "Signer = [string]$signature.SignerCertificate.Subject }; "
        "$out | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script, str(path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    raw = (result.stdout or "").strip()
    if result.returncode != 0 or not raw:
        return False, f"Could not verify Authenticode signature: {result.stderr.strip() or 'unknown error'}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Could not parse Authenticode verification result."
    status = str(payload.get("Status") or "").strip()
    if status != "Valid":
        return False, (
            "Authenticode signature verification failed: "
            f"{payload.get('StatusMessage') or status or 'unknown error'}"
        )
    return True, str(payload.get("Signer") or "Valid Authenticode signature")


def _helper_command(attempt_id: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(_host_path(sys.executable).resolve()), "--run-upgrade-helper", attempt_id]
    return [sys.executable, "-m", "mediamop.windows.updater_service", "--run-upgrade-helper", attempt_id]


def _launch_helper(attempt_id: str) -> subprocess.Popen[bytes]:
    creationflags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        creationflags |= int(getattr(subprocess, name, 0))
    return subprocess.Popen(
        _helper_command(attempt_id),
        cwd=str(_install_root()),
        close_fds=True,
        creationflags=creationflags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _launch_installer(installer_path: Path, *, installer_log_path: Path) -> subprocess.Popen[bytes]:
    creationflags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        creationflags |= int(getattr(subprocess, name, 0))
    cmd = [
        str(installer_path.resolve()),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        f"/LOG={installer_log_path}",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(installer_path.parent),
        close_fds=True,
        creationflags=creationflags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _copy_latest_installer_log(source: Path) -> None:
    try:
        latest = _latest_installer_log_path()
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    except OSError as exc:
        _append_service_log(f"Could not refresh latest installer log copy: {exc}")


def _read_runtime_port() -> int:
    path = _runtime_home() / "current-port.txt"
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return 8788
    try:
        port = int(raw)
    except ValueError:
        return 8788
    return port if 1 <= port <= 65535 else 8788


def _backend_urls(port: int) -> tuple[str, str]:
    return (f"http://127.0.0.1:{port}/ready", f"http://127.0.0.1:{port}/openapi.json")


def _probe_running_backend_version(port: int) -> tuple[bool, str | None, str | None]:
    ready_url, openapi_url = _backend_urls(port)
    try:
        ready_response = httpx.get(ready_url, timeout=3.0)
    except Exception as exc:
        return False, None, f"Could not reach {ready_url}: {exc}"
    if ready_response.status_code != 200:
        return False, None, f"{ready_url} returned HTTP {ready_response.status_code}."
    try:
        version_response = httpx.get(openapi_url, timeout=3.0)
        version_response.raise_for_status()
        payload = version_response.json()
    except Exception as exc:
        return True, None, f"Could not read backend version from {openapi_url}: {exc}"
    version_value = None
    if isinstance(payload, dict):
        info = payload.get("info")
        if isinstance(info, dict):
            version_value = str(info.get("version") or "").strip() or None
    return True, version_value, None


def _start_packaged_server(port: int) -> subprocess.Popen[bytes]:
    install_root = _install_root()
    server_exe = install_root / "MediaMopServer.exe"
    if not server_exe.is_file():
        raise FileNotFoundError(f"Bundled server host is missing: {server_exe}")
    creationflags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        creationflags |= int(getattr(subprocess, name, 0))
    return subprocess.Popen(
        [str(server_exe), "--serve", "--port", str(port)],
        cwd=str(install_root),
        close_fds=True,
        creationflags=creationflags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _required_install_paths(install_root: Path) -> list[tuple[str, Path]]:
    return [
        ("MediaMop.exe", install_root / "MediaMop.exe"),
        ("MediaMopServer.exe", install_root / "MediaMopServer.exe"),
        ("MediaMopUpdater.exe", install_root / "MediaMopUpdater.exe"),
        ("MediaMopUpdaterService.exe", install_root / "MediaMopUpdaterService.exe"),
        ("MediaMopUpdaterService.xml", install_root / "MediaMopUpdaterService.xml"),
        ("web-dist", install_root / "_internal" / "web-dist" / "index.html"),
    ]


def _collect_install_diagnostics(target_version: str, *, port: int) -> dict[str, object]:
    install_root = _install_root()
    packaged_root = install_root / "_internal"
    packaged_version = resolve_packaged_version(packaged_root)
    required_files = []
    missing_labels: list[str] = []
    for label, path in _required_install_paths(install_root):
        exists = path.exists()
        required_files.append({"label": label, "path": str(path), "exists": exists})
        if not exists:
            missing_labels.append(label)
    backend_ready, backend_version, backend_detail = _probe_running_backend_version(port)
    return {
        "required_files": required_files,
        "missing_required_files": missing_labels,
        "packaged_version": packaged_version,
        "backend_port": port,
        "backend_ready": backend_ready,
        "backend_version": backend_version,
        "backend_detail": backend_detail,
        "running_processes": _running_media_processes(),
        "target_version": target_version,
    }


def _verify_install(target_version: str) -> tuple[bool, dict[str, object], str]:
    port = _read_runtime_port()
    deadline = time.time() + _VERIFY_INSTALL_TIMEOUT_SECONDS
    started_server_pid: int | None = None
    last_diagnostics: dict[str, object] = _collect_install_diagnostics(target_version, port=port)
    while time.time() < deadline:
        diagnostics = _collect_install_diagnostics(target_version, port=port)
        diagnostics["restarted_server_pid"] = started_server_pid
        packaged_version = str(diagnostics.get("packaged_version") or "").strip() or None
        backend_ready = bool(diagnostics.get("backend_ready"))
        backend_version = str(diagnostics.get("backend_version") or "").strip() or None
        missing_required = diagnostics.get("missing_required_files")
        if packaged_version == target_version and not missing_required and backend_ready and backend_version == target_version:
            return True, diagnostics, f"Upgrade completed. Running version: {target_version}."
        if packaged_version == target_version and not missing_required and started_server_pid is None and not backend_ready:
            try:
                process = _start_packaged_server(port)
            except Exception as exc:
                diagnostics["server_restart_error"] = str(exc)
            else:
                started_server_pid = process.pid
                diagnostics["restarted_server_pid"] = process.pid
                _append_service_log(f"Restarted packaged MediaMop server for upgrade verification (pid={process.pid}, port={port}).")
        last_diagnostics = diagnostics
        time.sleep(_BACKEND_POLL_INTERVAL_SECONDS)
    backend_version = str(last_diagnostics.get("backend_version") or "").strip() or None
    packaged_version = str(last_diagnostics.get("packaged_version") or "").strip() or None
    if packaged_version != target_version:
        reason = (
            f"Installed package metadata still reports {packaged_version or 'unknown'} instead of {target_version}."
        )
    elif backend_version != target_version:
        reason = f"Running backend still reports {backend_version or 'unknown'} instead of {target_version}."
    else:
        reason = "MediaMop did not become ready with the expected version in time."
    return False, last_diagnostics, reason


def _perform_upgrade_attempt(attempt_id: str) -> None:
    state = _read_state()
    if str(state.get("attempt_id") or "").strip() != attempt_id:
        _append_service_log(f"Ignoring helper run for stale attempt {attempt_id}.")
        return
    target_version = normalize_release_version(str(state.get("target_version") or ""))
    if not target_version:
        _mark_failed(
            message="Upgrade failed.",
            last_error="Upgrade state did not include a target version.",
            diagnostics={"attempt_id": attempt_id},
        )
        return
    installer_log = _host_path(str(state.get("installer_log_path") or _installer_log_path(attempt_id)))
    installer_log.parent.mkdir(parents=True, exist_ok=True)
    installer_log.unlink(missing_ok=True)
    try:
        _transition_state(
            "checking",
            "Upgrade request accepted. MediaMop is checking release metadata.",
            target_version=target_version,
            diagnostics={"helper_pid": os.getpid(), "release_tag": f"v{target_version}"},
        )
        release = fetch_release_record_by_version(target_version, user_agent_version=__version__)
        installer_asset = release.asset_named(WINDOWS_INSTALLER_ASSET_NAME)
        if installer_asset is None:
            raise ValueError(f"Release v{target_version} does not include {WINDOWS_INSTALLER_ASSET_NAME}.")
        installer_url = _validated_asset_download_url(
            installer_asset.browser_download_url,
            version=target_version,
            asset_name=WINDOWS_INSTALLER_ASSET_NAME,
        )
        checksum_asset = release.asset_named(WINDOWS_INSTALLER_SHA256_ASSET_NAME)
        expected_sha256 = None
        if checksum_asset is not None:
            checksum_url = _validated_asset_download_url(
                checksum_asset.browser_download_url,
                version=target_version,
                asset_name=WINDOWS_INSTALLER_SHA256_ASSET_NAME,
            )
            checksum_text = _download_text(checksum_url)
            expected_sha256 = _parse_sha256_manifest(checksum_text)
        if not expected_sha256 and not _bool_env("MEDIAMOP_UPDATER_ALLOW_UNVERIFIED"):
            raise ValueError(
                "Release checksum manifest is missing or unreadable. Official in-app upgrades require "
                f"{WINDOWS_INSTALLER_SHA256_ASSET_NAME}."
            )

        _transition_state(
            "downloading",
            "Upgrade request accepted. MediaMop is downloading the installer.",
            target_version=target_version,
            expected_sha256=expected_sha256,
        )
        installer_path = _download_installer(
            installer_url,
            target_version=target_version,
            attempt_id=attempt_id,
        )
        _transition_state(
            "verifying_download",
            "Installer is being verified.",
            target_version=target_version,
            downloaded_installer_path=str(installer_path),
            expected_sha256=expected_sha256,
        )
        installer_sha256 = _sha256_for_path(installer_path)
        if expected_sha256 and installer_sha256.lower() != expected_sha256.lower():
            raise ValueError(
                f"Installer SHA-256 mismatch. Expected {expected_sha256}, got {installer_sha256}."
            )
        signature_ok, signature_detail = _verify_authenticode_signature(installer_path)
        if not signature_ok:
            raise ValueError(signature_detail)
        _transition_state(
            "installer_started",
            "Installer is starting.",
            target_version=target_version,
            downloaded_installer_path=str(installer_path),
            installer_sha256=installer_sha256,
            expected_sha256=expected_sha256,
            diagnostics={
                "signature_detail": signature_detail,
            },
        )
        process = _launch_installer(installer_path, installer_log_path=installer_log)
        _transition_state(
            "installer_running",
            "Installer is running. MediaMop may temporarily disconnect.",
            target_version=target_version,
            diagnostics={
                "installer_pid": process.pid,
            },
        )
        if getattr(sys, "frozen", False) and os.name == "nt":
            _append_service_log(
                "Installer launched from packaged updater; helper will exit and let updater-service "
                "reconciliation finish verification after installer/service restart."
            )
            return
        exit_code = process.wait(timeout=_INSTALLER_WAIT_TIMEOUT_SECONDS)
        _append_service_log(f"Installer process exited with code {exit_code}.")
        if exit_code != 0:
            if installer_log.is_file():
                _copy_latest_installer_log(installer_log)
            _mark_failed(
                message="Upgrade failed.",
                last_error=f"Installer exited with code {exit_code}.",
                target_version=target_version,
                diagnostics={
                    "installer_exit_code": exit_code,
                },
            )
            return
        if not installer_log.is_file():
            _mark_failed(
                message="Upgrade failed.",
                last_error="Installer exited successfully but did not produce an installer log.",
                target_version=target_version,
                diagnostics={
                    "installer_exit_code": exit_code,
                },
            )
            return
        _copy_latest_installer_log(installer_log)
        _transition_state(
            "restarting",
            "MediaMop is reconnecting and verifying the installed version.",
            target_version=target_version,
            diagnostics={
                "installer_exit_code": exit_code,
            },
        )
        _transition_state(
            "verifying_install",
            "MediaMop is reconnecting and verifying the installed version.",
            target_version=target_version,
        )
        verified, diagnostics, message = _verify_install(target_version)
        if verified:
            _transition_state(
                "completed",
                message,
                target_version=target_version,
                current_version_seen=target_version,
                last_completed_at=_iso_now(),
                last_error=None,
                diagnostics=diagnostics,
            )
            return
        _mark_failed(
            message="Upgrade failed.",
            last_error=message,
            target_version=target_version,
            current_version_seen=str(diagnostics.get("backend_version") or diagnostics.get("packaged_version") or __version__),
            diagnostics=diagnostics,
        )
    except Exception as exc:
        _mark_failed(
            message="Upgrade failed.",
            last_error=str(exc),
            target_version=target_version,
            diagnostics={"helper_pid": os.getpid()},
        )


def _reconcile_attempt_worker(attempt_id: str) -> None:
    try:
        state = _read_state()
        if str(state.get("attempt_id") or "").strip() != attempt_id:
            return
        phase = str(state.get("phase") or "").strip().lower()
        if phase not in _RECOVERABLE_PHASES:
            return
        diagnostics = state.get("diagnostics") if isinstance(state.get("diagnostics"), dict) else {}
        installer_pid = diagnostics.get("installer_pid") if isinstance(diagnostics, dict) else None
        if _pid_is_running(installer_pid):
            deadline = time.time() + _INSTALLER_WAIT_TIMEOUT_SECONDS
            while time.time() < deadline and _pid_is_running(installer_pid):
                time.sleep(_BACKEND_POLL_INTERVAL_SECONDS)
        target_version = normalize_release_version(str(state.get("target_version") or ""))
        if not target_version:
            _mark_failed(
                message="Upgrade failed.",
                last_error="Upgrade reconciliation could not find a target version.",
                diagnostics={"attempt_id": attempt_id},
            )
            return
        installer_log = _host_path(str(state.get("installer_log_path") or ""))
        if not installer_log.is_file():
            _mark_failed(
                message="Upgrade failed.",
                last_error="Installer exited but did not produce an installer log.",
                target_version=target_version,
                diagnostics={"reconciled_after_restart": True},
            )
            return
        _copy_latest_installer_log(installer_log)
        _transition_state(
            "restarting",
            "MediaMop is reconnecting and verifying the installed version.",
            target_version=target_version,
            diagnostics={"reconciled_after_restart": True},
        )
        _transition_state(
            "verifying_install",
            "MediaMop is reconnecting and verifying the installed version.",
            target_version=target_version,
            diagnostics={"reconciled_after_restart": True},
        )
        verified, diagnostics, message = _verify_install(target_version)
        if verified:
            _transition_state(
                "completed",
                message,
                target_version=target_version,
                current_version_seen=target_version,
                last_completed_at=_iso_now(),
                last_error=None,
                diagnostics=diagnostics,
            )
            return
        _mark_failed(
            message="Upgrade failed.",
            last_error=message,
            target_version=target_version,
            current_version_seen=str(diagnostics.get("backend_version") or diagnostics.get("packaged_version") or __version__),
            diagnostics=diagnostics,
        )
    finally:
        if _RECONCILE_LOCK.locked():
            try:
                _RECONCILE_LOCK.release()
            except RuntimeError:
                pass


def _maybe_reconcile_pending_attempt() -> None:
    state = _read_state()
    phase = str(state.get("phase") or "").strip().lower()
    if phase not in _ACTIVE_PHASES:
        return
    attempt_id = str(state.get("attempt_id") or "").strip()
    if not attempt_id:
        return
    diagnostics = state.get("diagnostics") if isinstance(state.get("diagnostics"), dict) else {}
    helper_pid = diagnostics.get("helper_pid") if isinstance(diagnostics, dict) else None
    installer_pid = diagnostics.get("installer_pid") if isinstance(diagnostics, dict) else None
    if _pid_is_running(helper_pid):
        return
    age = _state_age_seconds(state)
    if (
        age is not None
        and age >= _STALE_ATTEMPT_SECONDS
        and not _pid_is_running(installer_pid)
    ):
        _mark_failed(
            message="Upgrade failed.",
            last_error=f"Upgrade attempt stalled during {phase}.",
            target_version=str(state.get("target_version") or "").strip() or None,
            diagnostics={
                "stalled_phase": phase,
                "state_age_seconds": age,
            },
        )
        return
    if phase in _RECOVERABLE_PHASES:
        if _RECONCILE_LOCK.acquire(blocking=False):
            thread = threading.Thread(
                target=_reconcile_attempt_worker,
                args=(attempt_id,),
                daemon=True,
                name="mediamop-updater-reconcile",
            )
            thread.start()
        return


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_version: str = Field(min_length=1)


def create_updater_app() -> FastAPI:
    app = FastAPI(title="MediaMop Updater Service", version=__version__)
    _maybe_reconcile_pending_attempt()
    shared_token = _load_or_create_token()

    def _require_token(x_mediamop_updater_token: str | None = Header(default=None, alias="X-MediaMop-Updater-Token")) -> None:
        if x_mediamop_updater_token != shared_token:
            raise HTTPException(status_code=401, detail="Unauthorized updater request.")

    @app.get("/health")
    def health() -> dict[str, object]:
        state = _read_state()
        return {
            "ok": True,
            "version": __version__,
            "phase": state.get("phase"),
            "attempt_id": state.get("attempt_id"),
        }

    @app.get("/api/v1/status")
    def status(x_mediamop_updater_token: str | None = Header(default=None, alias="X-MediaMop-Updater-Token")) -> dict[str, object]:
        _require_token(x_mediamop_updater_token)
        _maybe_reconcile_pending_attempt()
        return _read_state()

    @app.post("/api/v1/apply")
    def apply_update(
        body: ApplyRequest,
        x_mediamop_updater_token: str | None = Header(default=None, alias="X-MediaMop-Updater-Token"),
    ) -> dict[str, object]:
        _require_token(x_mediamop_updater_token)
        if os.name != "nt":
            raise HTTPException(status_code=400, detail="Windows updater service can only run on Windows.")
        target_version = normalize_release_version(body.target_version)
        if not target_version:
            raise HTTPException(status_code=400, detail="Target version is missing.")
        with _APPLY_LOCK:
            current_state = _read_state()
            if _stable_or_active_attempt_exists(current_state):
                raise HTTPException(status_code=409, detail="A MediaMop upgrade is already in progress.")
            attempt_id = uuid.uuid4().hex
            with _STATE_LOCK:
                _persist_state(_fresh_attempt_state(target_version, attempt_id))
            try:
                helper = _launch_helper(attempt_id)
            except Exception as exc:
                _mark_failed(
                    message="Upgrade failed before launch.",
                    last_error=f"Could not launch upgrade helper: {exc}",
                    target_version=target_version,
                    diagnostics={"attempt_id": attempt_id},
                )
                raise HTTPException(status_code=500, detail="Failed to start MediaMop upgrade helper.") from exc
            _write_state(diagnostics={"helper_pid": helper.pid})
            _append_service_log(f"Upgrade helper launched for {target_version} (attempt_id={attempt_id}, pid={helper.pid}).")
            return {
                "accepted": True,
                "attempt_id": attempt_id,
                "target_version": target_version,
                "message": "Upgrade request accepted. MediaMop is checking release metadata.",
            }

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--run-upgrade-helper", dest="attempt_id")
    parser.add_argument("--version", action="store_true")
    args, _extra = parser.parse_known_args(argv)
    if args.version:
        print(__version__)
        return
    if args.attempt_id:
        _perform_upgrade_attempt(args.attempt_id)
        return
    app = create_updater_app()
    port = int((os.environ.get("MEDIAMOP_UPDATER_PORT") or str(UPDATER_PORT)).strip())
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", log_config=None)


if __name__ == "__main__":
    main()
