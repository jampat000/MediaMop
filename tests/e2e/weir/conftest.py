"""Weir spine E2E: SQLite and the uvicorn API serving the built web app, as the packages do.

Opt-in only: ``WEIR_E2E=1``. Every run gets its own data folder: a fresh temporary directory,
or a new ``run-…`` folder inside ``WEIR_E2E_HOME`` when that is set. Server start-up, teardown
and leftover clean-up live in ``_runtime.py`` (#462). Each server's output is kept in
``<home>/e2e-logs`` and quoted in the failure when a server does not come up.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.weir import _runtime as runtime


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "apps" / "backend" / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(
        "Weir E2E: cannot find repo root (apps/backend/pyproject.toml missing)"
    )


REPO_ROOT = _repo_root()
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
WEB_DIR = REPO_ROOT / "apps" / "web"
SRC_PATH = (BACKEND_DIR / "src").resolve()


def _truncate_auth_tables(home: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from tests.e2e.weir.utils import clear_auth_tables_for_home;"
                "clear_auth_tables_for_home(__import__('os').environ['WEIR_E2E_TRUNCATE_HOME'])"
            ),
        ],
        cwd=str(REPO_ROOT.resolve()),
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT.resolve()), str(SRC_PATH.resolve())]
            ),
            "WEIR_E2E_TRUNCATE_HOME": home,
        },
        check=True,
    )


def _run_backend_code(
    home: str, code: str, *, extra_env: dict[str, str] | None = None
) -> None:
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR.resolve()),
        env={
            **os.environ,
            "WEIR_BACKEND_SRC": str(SRC_PATH.resolve()),
            "WEIR_HOME": home,
            **(extra_env or {}),
        },
        check=True,
    )


@pytest.fixture(scope="session")
def weir_runtime() -> dict[str, str]:
    if os.environ.get("WEIR_E2E") != "1":
        pytest.skip("WEIR_E2E=1 required")
    secret = os.environ.get("WEIR_SESSION_SECRET", "").strip()
    if not secret:
        pytest.fail("WEIR_SESSION_SECRET must be set for Weir E2E")

    stopped = runtime.reap_leftovers()
    if stopped:
        print(f"Weir E2E: stopped servers left behind by an earlier run: {', '.join(stopped)}")

    home = runtime.run_home((os.environ.get("WEIR_E2E_HOME") or "").strip() or None)
    logs = Path(home) / "e2e-logs"
    api_port = runtime.pick_free_port()
    api_internal = f"http://127.0.0.1:{api_port}"
    # The API serves the built web app itself, exactly as the Docker and Windows packages do.
    # Going through `vite preview` added a proxy hop whose keep-alive race failed POSTs and PUTs
    # intermittently ("Failed to fetch") and made the suite untrustworthy (#462).
    web_origin = api_internal
    web_dist = WEB_DIR / "dist"
    if not (web_dist / "index.html").is_file():
        pytest.fail("Weir E2E needs the built web app: run `npm ci && npm run build` in apps/web first.")

    env_base = {
        **os.environ,
        "WEIR_HOME": home,
        "WEIR_SESSION_SECRET": secret,
        "WEIR_CORS_ORIGINS": web_origin,
        "PYTHONPATH": str(SRC_PATH),
        "WEIR_WEB_DIST": str(web_dist),
        # Every test signs up a fresh admin and signs in against this one API process. The
        # production limits (10 bootstraps an hour, 10 sign-ins a minute) are per process, so a
        # suite of more than ten tests was refused part-way through and failed as a stuck sign-in
        # (#462). The limits themselves are covered by the backend tests.
        "WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS": "10000",
        "WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS": "10000",
    }

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env_base,
        check=True,
    )
    _truncate_auth_tables(home)

    servers: list[runtime.Server] = []

    def _stop_all() -> None:
        for server in reversed(servers):
            runtime.stop_server(server)
        servers.clear()

    # Finalizers do not run if pytest itself is killed; this still runs on a normal interpreter exit.
    atexit.register(_stop_all)
    try:
        try:
            api = runtime.start_server(
                "Weir API",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "weir.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                    "--log-level",
                    "warning",
                ],
                cwd=BACKEND_DIR,
                env=env_base,
                port=api_port,
                url=f"{api_internal}/health",
                log_path=logs / "api.log",
            )
            servers.append(api)
            runtime.wait_until_up(api, timeout_s=60.0)
        except RuntimeError as exc:
            pytest.fail(f"Weir E2E could not start its server.\n{exc}", pytrace=False)

        yield {
            "base_url": web_origin,
            "api_url": api_internal,
            "home": home,
        }
    finally:
        _stop_all()
        atexit.unregister(_stop_all)


@pytest.fixture(scope="function", autouse=True)
def _reset_runtime_auth_state(weir_runtime: dict[str, str]) -> None:
    _truncate_auth_tables(weir_runtime["home"])


@pytest.fixture(scope="function")
def weir_shell(weir_runtime: dict[str, str]) -> str:
    return weir_runtime["base_url"]


@pytest.fixture(scope="function")
def weir_home(weir_runtime: dict[str, str]) -> str:
    return weir_runtime["home"]


@pytest.fixture()
def seed_activity_event(weir_home: str):
    def _seed(
        *, event_type: str, module: str, title: str, detail: str | None = None
    ) -> None:
        code = (
            "import os, sys\n"
            "sys.path.insert(0, os.environ['WEIR_BACKEND_SRC'])\n"
            "from weir.core.config import WeirSettings\n"
            "from weir.core.db import create_db_engine, create_session_factory\n"
            "from weir.platform.activity.models import ActivityEvent\n"
            "settings = WeirSettings.load()\n"
            "eng = create_db_engine(settings)\n"
            "fac = create_session_factory(eng)\n"
            "with fac() as db:\n"
            "    db.add(ActivityEvent(event_type=os.environ['MM_EVENT_TYPE'], module=os.environ['MM_MODULE'], title=os.environ['MM_TITLE'], detail=os.environ.get('MM_DETAIL') or None))\n"
            "    db.commit()\n"
            "eng.dispose()\n"
        )
        _run_backend_code(
            weir_home,
            code,
            extra_env={
                "MM_EVENT_TYPE": event_type,
                "MM_MODULE": module,
                "MM_TITLE": title,
                "MM_DETAIL": detail or "",
            },
        )

    return _seed
