"""Headless server entry point for the MediaMop Windows package.

Launched by the .NET tray app via ``MediaMopServer.exe --serve --port <port>``.
Handles environment setup, database migrations, and the uvicorn server loop.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path

import uvicorn

from mediamop.api.factory import create_app
from mediamop.version import __version__


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


def _ensure_session_secret(runtime_home: Path) -> str:
    secret_path = runtime_home / "session.secret"
    if secret_path.is_file():
        existing = secret_path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    runtime_home.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(48)
    secret_path.write_text(token, encoding="utf-8")
    return token


def _prepare_environment(resource_root: Path, runtime_home: Path) -> None:
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


def _run_migrations(resource_root: Path) -> None:
    from alembic.config import Config

    from alembic import command

    alembic_ini = resource_root / "alembic.ini"
    alembic_dir = resource_root / "alembic"
    if not alembic_ini.is_file() or not alembic_dir.is_dir():
        raise RuntimeError("Bundled migration assets are missing from the MediaMop desktop package.")
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_dir))
    command.upgrade(cfg, "head")


def main() -> None:
    if "--version" in sys.argv:
        print(__version__)
        return

    port = 8788
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 >= len(sys.argv):
            raise RuntimeError("Missing value for --port.")
        port = int(sys.argv[idx + 1])

    resource_root = _resource_root()
    runtime_home = _runtime_home()
    _prepare_environment(resource_root, runtime_home)
    _run_migrations(resource_root)
    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            log_config=None,
        )
    )
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
