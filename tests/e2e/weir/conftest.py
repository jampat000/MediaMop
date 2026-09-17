"""Weir spine E2E: the .NET server serving the built web app over SQLite, as the packages do.

Opt-in only: ``WEIR_E2E=1``. Every run gets its own data folder: a fresh temporary directory,
or a new ``run-…`` folder inside ``WEIR_E2E_HOME`` when that is set. Server start-up, teardown
and leftover clean-up live in ``_runtime.py`` (#462). Each server's output is kept in
``<home>/e2e-logs`` and quoted in the failure when a server does not come up.

The server is ``dotnet run --project apps/server/src/Weir.Host --no-build`` (build it first), or the
published executable named by ``WEIR_E2E_SERVER_EXE``. Nothing here imports Weir: seeding and resets
are plain SQL against the SQLite file (``utils.py``).
"""

from __future__ import annotations

import atexit
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from tests.e2e.weir import _runtime as runtime
from tests.e2e.weir.utils import clear_auth_tables_for_home, db_path_for_home, insert_activity_event

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_DIR = REPO_ROOT / "apps" / "web"
SERVER_PROJECT = REPO_ROOT / "apps" / "server" / "src" / "Weir.Host"


def _ledger_for_this_checkout() -> Path:
    """Several checkouts on one machine (parallel worktrees) must not reap each other's E2E servers."""

    explicit = (os.environ.get("WEIR_E2E_LEDGER") or "").strip()
    if explicit:
        return Path(explicit)
    checksum = hashlib.sha1(str(REPO_ROOT.resolve()).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return Path(tempfile.gettempdir()) / f"weir-e2e-servers-{checksum}.json"


runtime.LEDGER = _ledger_for_this_checkout()


def _server_command(port: int) -> tuple[list[str], Path]:
    listen = ["--host", "127.0.0.1", "--port", str(port)]
    exe = (os.environ.get("WEIR_E2E_SERVER_EXE") or "").strip()
    if exe:
        if not Path(exe).is_file():
            pytest.fail(f"WEIR_E2E_SERVER_EXE points at {exe}, which does not exist.")
        return [exe, *listen], Path(exe).parent
    if shutil.which("dotnet") is None:
        pytest.fail("Weir E2E needs the dotnet CLI on PATH (or WEIR_E2E_SERVER_EXE).")
    return ["dotnet", "run", "--project", str(SERVER_PROJECT), "--no-build", "--", *listen], REPO_ROOT


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
    # The server serves the built web app itself, exactly as the Docker and Windows packages do.
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
        "WEIR_WEB_DIST": str(web_dist),
        # Every test signs up a fresh admin and signs in against this one server process. The
        # production limits (10 bootstraps an hour, 10 sign-ins a minute) are per process, so a
        # suite of more than ten tests was refused part-way through and failed as a stuck sign-in
        # (#462). The limits themselves are covered by the contract suite.
        "WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS": "10000",
        "WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS": "10000",
    }
    env_base.pop("WEIR_ENV", None)

    servers: list[runtime.Server] = []

    def _stop_all() -> None:
        for server in reversed(servers):
            runtime.stop_server(server)
        servers.clear()

    # Finalizers do not run if pytest itself is killed; this still runs on a normal interpreter exit.
    atexit.register(_stop_all)
    try:
        try:
            command, cwd = _server_command(api_port)
            api = runtime.start_server(
                "Weir API",
                command,
                cwd=cwd,
                env=env_base,
                port=api_port,
                url=f"{api_internal}/health",
                log_path=logs / "api.log",
            )
            servers.append(api)
            runtime.wait_until_up(api, timeout_s=90.0)
        except RuntimeError as exc:
            pytest.fail(f"Weir E2E could not start its server.\n{exc}", pytrace=False)

        # The server creates and migrates its database on start; tests begin from a clean one.
        if not db_path_for_home(home).is_file():
            pytest.fail(f"Weir E2E: the server did not create its database at {db_path_for_home(home)}.")
        clear_auth_tables_for_home(home)

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
    clear_auth_tables_for_home(weir_runtime["home"])


@pytest.fixture(scope="function")
def weir_shell(weir_runtime: dict[str, str]) -> str:
    return weir_runtime["base_url"]


@pytest.fixture(scope="function")
def weir_home(weir_runtime: dict[str, str]) -> str:
    return weir_runtime["home"]


@pytest.fixture()
def seed_activity_event(weir_home: str):
    def _seed(*, event_type: str, module: str, title: str, detail: str | None = None) -> None:
        insert_activity_event(weir_home, event_type=event_type, module=module, title=title, detail=detail)

    return _seed
