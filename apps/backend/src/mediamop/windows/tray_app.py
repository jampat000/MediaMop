"""Windows tray host for packaged MediaMop builds.

Runs the FastAPI app in the user session, serves the bundled web UI, and exposes
basic tray actions. This avoids Windows-service filesystem limitations for NAS or
external-drive access.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from contextlib import closing
from pathlib import Path
from typing import Any

import uvicorn
from alembic import command
from alembic.config import Config
from mediamop.api.factory import create_app

_LOG_LOCK = threading.Lock()


def _fallback_log_path() -> Path:
    return _runtime_home() / "tray-host.log"


def _append_fallback_log(message: str) -> None:
    path = _fallback_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with _LOG_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        executable_dir = Path(sys.executable).resolve().parent
        internal_dir = executable_dir / "_internal"
        if internal_dir.is_dir():
            return internal_dir
        return executable_dir
    return Path(__file__).resolve().parents[5]


def _runtime_home() -> Path:
    raw = (os.environ.get("MEDIAMOP_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    program_data = (os.environ.get("PROGRAMDATA") or r"C:\ProgramData").strip()
    return Path(program_data) / "MediaMop"


def _find_free_port(preferred: int = 8788) -> int:
    for port in range(preferred, preferred + 20):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Could not find a free localhost port for MediaMop.")


def _ensure_session_secret(runtime_home: Path) -> str:
    secret_path = runtime_home / "session.secret"
    if secret_path.is_file():
        existing = secret_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    runtime_home.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(48)
    _write_private_runtime_token(secret_path, token)
    return token


def _write_private_runtime_token(path: Path, value: str) -> None:
    """Persist the local session token with owner-only permissions where supported."""

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


def _prepare_environment(resource_root: Path, runtime_home: Path) -> Path:
    web_dist = resource_root / "web-dist"
    if not (web_dist / "index.html").is_file():
        raise RuntimeError("Bundled web assets are missing from the MediaMop desktop package.")
    runtime_home.mkdir(parents=True, exist_ok=True)
    os.environ["MEDIAMOP_ENV"] = "production"
    os.environ["MEDIAMOP_HOME"] = str(runtime_home)
    os.environ["MEDIAMOP_WEB_DIST"] = str(web_dist)
    os.environ["MEDIAMOP_ALEMBIC_ROOT"] = str(resource_root)
    os.environ["MEDIAMOP_SESSION_COOKIE_SECURE"] = "false"
    os.environ["MEDIAMOP_SESSION_SECRET"] = _ensure_session_secret(runtime_home)
    return web_dist


def _run_migrations(resource_root: Path) -> None:
    alembic_ini = resource_root / "alembic.ini"
    alembic_dir = resource_root / "alembic"
    if not alembic_ini.is_file() or not alembic_dir.is_dir():
        raise RuntimeError("Bundled migration assets are missing from the MediaMop desktop package.")
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_dir))
    command.upgrade(cfg, "head")


def _open_browser(port: int) -> None:
    webbrowser.open(f"http://127.0.0.1:{port}/", new=2)


def _wait_for_health(port: int, timeout_seconds: float = 30.0) -> None:
    import http.client

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/health")
            response = conn.getresponse()
            if response.status == 200:
                return
        except OSError:
            time.sleep(0.35)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    raise RuntimeError("MediaMop did not start listening on localhost in time.")


def _load_icon(resource_root: Path) -> Any:
    from PIL import Image, ImageDraw

    candidates = [
        resource_root / "assets" / "mediamop-tray-icon.png",
        resource_root / "assets" / "mediamop-logo-premium.png",
        resource_root / "mediamop-logo-premium.png",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return Image.open(candidate).convert("RGBA").resize((64, 64))
    image = Image.new("RGBA", (64, 64), (15, 18, 24, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=12, fill=(212, 175, 55, 255))
    draw.text((18, 20), "M", fill=(17, 17, 17, 255))
    return image


class _MediaMopTrayApp:
    def __init__(self) -> None:
        self._resource_root = _resource_root()
        self._runtime_home = _runtime_home()
        self._runtime_home.mkdir(parents=True, exist_ok=True)
        self._log_path = self._runtime_home / "tray-host.log"
        self._port = _find_free_port(8788)
        self._log(f"Starting tray host. resource_root={self._resource_root} runtime_home={self._runtime_home}")
        _prepare_environment(self._resource_root, self._runtime_home)
        (self._runtime_home / "current-port.txt").write_text(str(self._port), encoding="utf-8")
        self._log(f"Prepared runtime environment on port {self._port}")
        _run_migrations(self._resource_root)
        self._log("Database migrations completed")
        self._icon: Any = None
        executable_dir = Path(sys.executable).resolve().parent
        self._server_exe = executable_dir / "MediaMopServer.exe"
        self._server_process: subprocess.Popen[str] | None = None

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with _LOG_LOCK:
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{timestamp}] {message}\n")

    def _handle_open(self, icon: Any, item: Any) -> None:  # noqa: ARG002
        _open_browser(self._port)

    def _handle_open_data_folder(self, icon: Any, item: Any) -> None:  # noqa: ARG002
        os.startfile(str(self._runtime_home))  # type: ignore[attr-defined]

    def _handle_quit(self, icon: Any, item: Any) -> None:  # noqa: ARG002
        self._log("Quit requested from tray icon")
        self._stop_server_process()
        icon.stop()

    def _create_icon(self) -> Any:
        import pystray
        from pystray import MenuItem as Item

        self._log("Creating tray icon")
        return pystray.Icon(
            "MediaMop",
            _load_icon(self._resource_root),
            "MediaMop",
            menu=pystray.Menu(
                Item("Open MediaMop", self._handle_open),
                Item("Open Data Folder", self._handle_open_data_folder),
                Item("Quit", self._handle_quit),
            ),
        )

    def _start_server_process(self) -> None:
        if not self._server_exe.is_file():
            raise RuntimeError(f"Bundled server host is missing: {self._server_exe}")
        self._log(f"Starting bundled server host: {self._server_exe}")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._server_process = subprocess.Popen(
            [str(self._server_exe), "--serve", "--port", str(self._port)],
            cwd=str(self._server_exe.parent),
            creationflags=creationflags,
        )
        self._log(f"Bundled server host pid={self._server_process.pid}")

    def _stop_server_process(self) -> None:
        proc = self._server_process
        if proc is None:
            return
        if proc.poll() is not None:
            return
        self._log(f"Stopping bundled server host pid={proc.pid}")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._log(f"Bundled server host pid={proc.pid} did not exit in time; killing it")
            proc.kill()
            proc.wait(timeout=5)
        finally:
            self._server_process = None

    def run(self) -> None:
        try:
            self._start_server_process()
            self._log("Waiting for local health endpoint")
            _wait_for_health(self._port)
            self._log(f"MediaMop is healthy on http://127.0.0.1:{self._port}/")
            _open_browser(self._port)
            self._icon = self._create_icon()
            self._log("Starting tray icon event loop")
            self._icon.run()
        except Exception:
            self._log("Tray host failed during startup:\n" + traceback.format_exc())
            self._stop_server_process()
            raise
        finally:
            self._stop_server_process()


def _run_server_mode(port: int) -> None:
    resource_root = _resource_root()
    runtime_home = _runtime_home()
    _prepare_environment(resource_root, runtime_home)
    _run_migrations(resource_root)
    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",
            log_config=None,
        )
    )
    asyncio.run(server.serve())


def main() -> None:
    try:
        if "--serve" in sys.argv:
            port = 8788
            if "--port" in sys.argv:
                idx = sys.argv.index("--port")
                if idx + 1 >= len(sys.argv):
                    raise RuntimeError("Missing value for --port.")
                port = int(sys.argv[idx + 1])
            _run_server_mode(port)
            return
        app = _MediaMopTrayApp()
        app.run()
    except Exception:
        _append_fallback_log("Fatal startup error:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
