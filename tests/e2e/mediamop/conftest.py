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
NPM_CMD = "npm.cmd" if os.name == "nt" else "npm"


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
    """Clear auth rows in a **subprocess** (same pattern as Alembic).

    The pytest parent process can still fail ``import mediamop`` on CI (editable hooks,
    importlib mode, sys.path ordering). A fresh ``python -c`` with an explicit ``src``
    prefix matches the working uvicorn/alembic children.
    """

    src = str(SRC_PATH.resolve())
    code = (
        "import os, sys\n"
        "sys.path.insert(0, os.environ['MEDIAMOP_BACKEND_SRC'])\n"
        "os.environ['MEDIAMOP_HOME'] = os.environ['MEDIAMOP_E2E_TRUNCATE_HOME']\n"
        "from sqlalchemy import delete\n"
        "from mediamop.core.config import MediaMopSettings\n"
        "from mediamop.core.db import create_db_engine, create_session_factory\n"
        "from mediamop.platform.auth.models import User, UserSession\n"
        "settings = MediaMopSettings.load()\n"
        "eng = create_db_engine(settings)\n"
        "fac = create_session_factory(eng)\n"
        "with fac() as db:\n"
        "    db.execute(delete(UserSession))\n"
        "    db.execute(delete(User))\n"
        "    db.commit()\n"
        "eng.dispose()\n"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR.resolve()),
        env={
            **os.environ,
            "MEDIAMOP_BACKEND_SRC": src,
            "MEDIAMOP_E2E_TRUNCATE_HOME": home,
        },
        check=True,
    )


def _run_backend_code(home: str, code: str, *, extra_env: dict[str, str] | None = None) -> None:
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR.resolve()),
        env={
            **os.environ,
            "MEDIAMOP_BACKEND_SRC": str(SRC_PATH.resolve()),
            "MEDIAMOP_HOME": home,
            **(extra_env or {}),
        },
        check=True,
    )


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


@pytest.fixture(scope="function")
def mediamop_runtime() -> dict[str, str]:
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
        [sys.executable, "-m", "alembic", "upgrade", "head"],
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
            NPM_CMD,
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
        yield {
            "base_url": web_origin,
            "api_url": api_internal,
            "home": home,
        }
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


@pytest.fixture(scope="function")
def mediamop_shell(mediamop_runtime: dict[str, str]) -> str:
    return mediamop_runtime["base_url"]


@pytest.fixture(scope="function")
def mediamop_home(mediamop_runtime: dict[str, str]) -> str:
    return mediamop_runtime["home"]


@pytest.fixture()
def seed_activity_event(mediamop_home: str):
    def _seed(*, event_type: str, module: str, title: str, detail: str | None = None) -> None:
        code = (
            "import os, sys\n"
            "sys.path.insert(0, os.environ['MEDIAMOP_BACKEND_SRC'])\n"
            "from mediamop.core.config import MediaMopSettings\n"
            "from mediamop.core.db import create_db_engine, create_session_factory\n"
            "from mediamop.platform.activity.models import ActivityEvent\n"
            "settings = MediaMopSettings.load()\n"
            "eng = create_db_engine(settings)\n"
            "fac = create_session_factory(eng)\n"
            "with fac() as db:\n"
            "    db.add(ActivityEvent(event_type=os.environ['MM_EVENT_TYPE'], module=os.environ['MM_MODULE'], title=os.environ['MM_TITLE'], detail=os.environ.get('MM_DETAIL') or None))\n"
            "    db.commit()\n"
            "eng.dispose()\n"
        )
        _run_backend_code(
            mediamop_home,
            code,
            extra_env={
                "MM_EVENT_TYPE": event_type,
                "MM_MODULE": module,
                "MM_TITLE": title,
                "MM_DETAIL": detail or "",
            },
        )

    return _seed
