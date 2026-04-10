"""MediaMop spine E2E: SQLite, uvicorn API, Vite preview (proxied /api).

Opt-in only: ``MEDIAMOP_E2E=1``. Uses ``MEDIAMOP_E2E_HOME`` when set, else a fresh temp directory for an isolated database file.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "apps" / "backend" / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("MediaMop E2E: cannot find repo root (apps/backend/pyproject.toml missing)")


REPO_ROOT = _repo_root()
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
WEB_DIR = REPO_ROOT / "apps" / "web"
SRC_PATH = (BACKEND_DIR / "src").resolve()


def _ensure_backend_src_on_path() -> None:
    """Match subprocess env (``PYTHONPATH``) so in-process imports see ``mediamop``."""

    src = str(SRC_PATH.resolve())
    while src in sys.path:
        sys.path.remove(src)
    sys.path.insert(0, src)


def _pick_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _e2e_home() -> str:
    explicit = (os.environ.get("MEDIAMOP_E2E_HOME") or "").strip()
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    return str(Path(tempfile.mkdtemp(prefix="mediamop_e2e_")))


def _truncate_auth_tables(home: str) -> None:
    _ensure_backend_src_on_path()
    os.environ["MEDIAMOP_HOME"] = home
    from sqlalchemy import delete

    from mediamop.core.config import MediaMopSettings
    from mediamop.core.db import create_db_engine, create_session_factory
    from mediamop.platform.auth.models import User, UserSession

    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.commit()
    eng.dispose()


def _wait_http(url: str, *, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(0.25)
    raise RuntimeError(f"timeout waiting for {url}: {last!r}")


@pytest.fixture(scope="session")
def mediamop_shell() -> str:
    if os.environ.get("MEDIAMOP_E2E") != "1":
        pytest.skip("MEDIAMOP_E2E=1 required")
    secret = os.environ.get("MEDIAMOP_SESSION_SECRET", "").strip()
    if not secret:
        pytest.fail("MEDIAMOP_SESSION_SECRET must be set for MediaMop E2E")

    home = _e2e_home()
    api_port = _pick_loopback_port()
    web_port = _pick_loopback_port()
    web_origin = f"http://127.0.0.1:{web_port}"
    api_internal = f"http://127.0.0.1:{api_port}"

    env_base = {
        **os.environ,
        "MEDIAMOP_HOME": home,
        "MEDIAMOP_SESSION_SECRET": secret,
        "MEDIAMOP_CORS_ORIGINS": web_origin,
        "PYTHONPATH": str(SRC_PATH),
    }

    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env_base,
        check=True,
    )
    _truncate_auth_tables(home)

    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "mediamop.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        env=env_base,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http(f"{api_internal}/health")
    except Exception:
        api_proc.terminate()
        pytest.fail("MediaMop API did not start")

    web_env = {
        **os.environ,
        "VITE_DEV_API_PROXY_TARGET": api_internal,
    }
    web_proc = subprocess.Popen(
        [
            "npm",
            "run",
            "preview",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(web_port),
            "--strictPort",
        ],
        cwd=str(WEB_DIR),
        env=web_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http(web_origin, timeout_s=90.0)
    except Exception:
        web_proc.terminate()
        api_proc.terminate()
        pytest.fail("Vite preview did not start (run npm install && npm run build in apps/web first)")

    try:
        yield web_origin
    finally:
        web_proc.terminate()
        try:
            web_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            web_proc.kill()
        api_proc.terminate()
        try:
            api_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            api_proc.kill()
