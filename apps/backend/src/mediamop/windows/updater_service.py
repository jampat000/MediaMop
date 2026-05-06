"""Dedicated local Windows updater service for premium in-app upgrades."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from mediamop.version import __version__

UPDATER_PORT = 8791
_STATE_LOCK = threading.Lock()
_JOB_LOCK = threading.Lock()


def _runtime_home() -> Path:
    raw = (os.environ.get("MEDIAMOP_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    program_data = (os.environ.get("PROGRAMDATA") or r"C:\ProgramData").strip()
    return Path(program_data) / "MediaMop"


def _install_root() -> Path:
    if getattr(sys, "frozen", False) and os.name == "nt":
        resolved = Path(sys.executable).resolve().parent
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


def _setup_log_path() -> Path:
    return _upgrade_root() / "installer-latest.log"


def _service_log_path() -> Path:
    return _upgrade_root() / "updater-service.log"


def _write_private_token(path: Path, value: str) -> None:
    if os.name == "nt":
        path.write_text(value, encoding="utf-8")
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
        return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(48)
    _write_private_token(path, token)
    return token


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _default_state() -> dict[str, object]:
    return {
        "phase": "idle",
        "message": "Updater ready.",
        "target_version": None,
        "installer_log_path": str(_setup_log_path()),
        "last_started_at": None,
        "last_completed_at": None,
        "last_error": None,
    }


def _read_state() -> dict[str, object]:
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
        }
    except json.JSONDecodeError as exc:
        _append_service_log(f"Updater state parse failed at {path}: {exc}")
        return {
            **_default_state(),
            "phase": "state_corrupt",
            "message": "Updater state file is unreadable.",
            "last_error": f"Could not parse updater state file: {exc}",
        }
    if not isinstance(raw, dict):
        _append_service_log(f"Updater state parse failed at {path}: expected JSON object.")
        return {
            **_default_state(),
            "phase": "state_corrupt",
            "message": "Updater state file is unreadable.",
            "last_error": "Could not parse updater state file: expected a JSON object.",
        }
    return {**_default_state(), **raw}


def _write_state(**updates: object) -> dict[str, object]:
    with _STATE_LOCK:
        state = _read_state()
        state.update(updates)
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        return state


def _append_service_log(message: str) -> None:
    path = _service_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def _validate_installer_url(installer_url: str) -> str:
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
    if not parsed.path.lower().endswith("/mediamopsetup.exe"):
        msg = "Installer download URL must point to MediaMopSetup.exe."
        raise ValueError(msg)
    return installer_url


def _launch_installer_detached(installer_path: Path) -> subprocess.Popen[bytes]:
    if os.name != "nt":
        msg = "Windows only"
        raise OSError(msg)
    create_breakaway_from_job = 0x01000000
    detached_process = 0x00000008
    create_new_process_group = 0x00000200
    create_no_window = 0x08000000
    flags = create_breakaway_from_job | detached_process | create_new_process_group | create_no_window
    cmd = [
        str(installer_path.resolve()),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        "/RESTARTAPPLICATIONS",
        f'/LOG="{_setup_log_path()}"',
    ]
    return subprocess.Popen(
        cmd,
        close_fds=True,
        creationflags=flags,
        cwd=str(installer_path.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _download_installer(installer_url: str, target_version: str) -> Path:
    target = _upgrade_root() / f"MediaMopSetup-{target_version}.exe"
    tmp = target.with_suffix(".download")
    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": f"MediaMopUpdater/{__version__}",
    }
    total = 0
    with httpx.stream("GET", installer_url, timeout=600.0, follow_redirects=True, headers=headers) as response:
        response.raise_for_status()
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                total += len(chunk)
                handle.write(chunk)
    if total < 512 * 1024:
        tmp.unlink(missing_ok=True)
        msg = "Downloaded installer is too small to be valid."
        raise ValueError(msg)
    tmp.replace(target)
    return target


def _apply_update_job(installer_url: str, target_version: str) -> None:
    try:
        _append_service_log(f"Upgrade request accepted for {target_version}.")
        installer_log_path = _setup_log_path()
        installer_log_path.parent.mkdir(parents=True, exist_ok=True)
        installer_log_path.unlink(missing_ok=True)
        _write_state(
            phase="downloading",
            message=f"Downloading MediaMop {target_version}.",
            target_version=target_version,
            installer_log_path=str(installer_log_path),
            last_started_at=_iso_now(),
            last_error=None,
        )
        installer_path = _download_installer(installer_url, target_version)
        _append_service_log(f"Downloaded installer to {installer_path}.")
        _write_state(
            phase="installer_started",
            message=f"Launching MediaMop {target_version} installer.",
            target_version=target_version,
            installer_log_path=str(installer_log_path),
            last_error=None,
        )
        process = _launch_installer_detached(installer_path)
        _append_service_log(f"Installer launched (pid={process.pid}).")
        _write_state(
            phase="installer_running",
            message=f"MediaMop {target_version} installer is running.",
            target_version=target_version,
            installer_log_path=str(installer_log_path),
            last_error=None,
        )
        exit_code = process.wait(timeout=3600)
        if exit_code != 0:
            msg = f"Installer exited with code {exit_code}."
            _append_service_log(msg)
            _write_state(
                phase="failed",
                message="Upgrade failed.",
                target_version=target_version,
                installer_log_path=str(installer_log_path),
                last_completed_at=_iso_now(),
                last_error=msg,
            )
            return
        if not installer_log_path.is_file():
            msg = (
                "Installer exited successfully but did not produce installer-latest.log. "
                "Upgrade outcome cannot be verified."
            )
            _append_service_log(msg)
            _write_state(
                phase="failed",
                message="Upgrade failed.",
                target_version=target_version,
                installer_log_path=str(installer_log_path),
                last_completed_at=_iso_now(),
                last_error=msg,
            )
            return
        _append_service_log("Installer completed successfully.")
        _write_state(
            phase="completed",
            message=f"MediaMop {target_version} upgrade completed.",
            target_version=target_version,
            installer_log_path=str(installer_log_path),
            last_completed_at=_iso_now(),
            last_error=None,
        )
    except Exception as exc:
        _append_service_log(f"Upgrade failed: {exc}")
        _write_state(
            phase="failed",
            message="Upgrade failed.",
            target_version=target_version,
            installer_log_path=str(_setup_log_path()),
            last_completed_at=_iso_now(),
            last_error=str(exc),
        )
    finally:
        if _JOB_LOCK.locked():
            _JOB_LOCK.release()


class ApplyRequest(BaseModel):
    installer_url: str = Field(min_length=1)
    target_version: str = Field(min_length=1)


def create_updater_app() -> FastAPI:
    app = FastAPI(title="MediaMop Updater Service", version=__version__)
    shared_token = _load_or_create_token()

    def _require_token(x_mediamop_updater_token: str | None = Header(default=None, alias="X-MediaMop-Updater-Token")) -> None:
        if x_mediamop_updater_token != shared_token:
            raise HTTPException(status_code=401, detail="Unauthorized updater request.")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "version": __version__,
            "phase": _read_state().get("phase"),
        }

    @app.get("/api/v1/status")
    def status(x_mediamop_updater_token: str | None = Header(default=None, alias="X-MediaMop-Updater-Token")) -> dict[str, object]:
        _require_token(x_mediamop_updater_token)
        return _read_state()

    @app.post("/api/v1/apply")
    def apply_update(
        body: ApplyRequest,
        x_mediamop_updater_token: str | None = Header(default=None, alias="X-MediaMop-Updater-Token"),
    ) -> dict[str, object]:
        _require_token(x_mediamop_updater_token)
        if os.name != "nt":
            raise HTTPException(status_code=400, detail="Windows updater service can only run on Windows.")
        try:
            installer_url = _validate_installer_url(body.installer_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not _JOB_LOCK.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="A MediaMop upgrade is already in progress.")
        thread = threading.Thread(
            target=_apply_update_job,
            args=(installer_url, body.target_version),
            daemon=True,
            name="mediamop-updater-apply",
        )
        try:
            thread.start()
        except Exception as exc:
            _JOB_LOCK.release()
            _append_service_log(f"Upgrade failed to start worker thread: {exc}")
            _write_state(
                phase="failed",
                message="Upgrade failed before launch.",
                target_version=body.target_version,
                installer_log_path=str(_setup_log_path()),
                last_completed_at=_iso_now(),
                last_error=f"Failed to start updater worker thread: {exc}",
            )
            raise HTTPException(status_code=500, detail="Failed to start MediaMop updater worker.") from exc
        return {
            "accepted": True,
            "message": "Upgrade started using the MediaMop updater service. MediaMop will close, install the update, and reopen.",
        }

    return app


def main() -> None:
    app = create_updater_app()
    port = int((os.environ.get("MEDIAMOP_UPDATER_PORT") or str(UPDATER_PORT)).strip())
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", log_config=None)


if __name__ == "__main__":
    main()
