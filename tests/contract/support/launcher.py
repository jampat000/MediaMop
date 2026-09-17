"""Start, stop, restart and kill the Weir server under test.

The suite never imports Weir. It starts the server as a separate process, talks to it over HTTP,
and reads the SQLite file only while the server is stopped. Which server runs is chosen by
``WEIR_CONTRACT_SERVER``:

- ``python`` (default): ``alembic upgrade head`` then ``uvicorn weir.api.main:app``, the same way
  the E2E harness starts it (``tests/e2e/weir/conftest.py``).
- ``dotnet``: ``dotnet run --project apps/server/src/Weir.Host --no-build -- --host 127.0.0.1 --port N``, or the published
  executable named by ``WEIR_CONTRACT_DOTNET_EXE``. The .NET server owns its own migrations, so
  "migrate" for it means one start-and-stop.

Process-tree teardown, the port guard, and the ledger that reaps servers an aborted run left
behind all come from the E2E runtime helpers (#462). The contract suite keeps its own ledger file
(``WEIR_CONTRACT_LEDGER`` overrides it) so an E2E run and a contract run never stop each other's
servers.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
WEB_DIST = REPO_ROOT / "apps" / "web" / "dist"
DOTNET_PROJECT = REPO_ROOT / "apps" / "server" / "src" / "Weir.Host"

DEFAULT_SESSION_SECRET = "contract-suite-session-secret-at-least-32-chars"
SERVER_KINDS = ("python", "dotnet")


def _load_runtime() -> ModuleType:
    """The E2E runtime helpers, loaded by path so this works from any rootdir or import mode."""

    path = REPO_ROOT / "tests" / "e2e" / "weir" / "_runtime.py"
    spec = importlib.util.spec_from_file_location("weir_e2e_runtime_for_contract", path)
    if spec is None or spec.loader is None:  # pragma: no cover - the file is in the repo
        raise RuntimeError(f"Cannot load the E2E runtime helpers from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    ledger = (os.environ.get("WEIR_CONTRACT_LEDGER") or "").strip()
    module.LEDGER = Path(ledger) if ledger else Path(tempfile.gettempdir()) / "weir-contract-servers.json"
    return module


runtime = _load_runtime()


def server_kind() -> str:
    kind = (os.environ.get("WEIR_CONTRACT_SERVER") or "python").strip().lower()
    if kind not in SERVER_KINDS:
        raise RuntimeError(f"WEIR_CONTRACT_SERVER must be one of {', '.join(SERVER_KINDS)}; got {kind!r}.")
    return kind


def python_executable() -> str:
    """The interpreter that has Weir installed: ``WEIR_CONTRACT_PYTHON``, the backend venv, or this one."""

    explicit = (os.environ.get("WEIR_CONTRACT_PYTHON") or "").strip()
    if explicit:
        return explicit
    venv = BACKEND_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv.is_file():
        return str(venv)
    return sys.executable


def dotnet_unavailable_reason() -> str | None:
    """Why the .NET server cannot be started here, or None when it can."""

    exe = (os.environ.get("WEIR_CONTRACT_DOTNET_EXE") or "").strip()
    if exe:
        return None if Path(exe).is_file() else f"WEIR_CONTRACT_DOTNET_EXE points at {exe}, which does not exist."
    if not DOTNET_PROJECT.is_dir():
        return (
            f"The .NET server project {DOTNET_PROJECT.relative_to(REPO_ROOT)} does not exist yet "
            "(it is scaffolded by #515), so there is nothing to run the contract against."
        )
    if shutil.which("dotnet") is None:
        return "The dotnet CLI is not on PATH."
    return None


@dataclass
class ServerUnderTest:
    """One Weir server with its own data folder. Restartable; the data folder survives restarts."""

    home: Path
    env_overrides: dict[str, str] = field(default_factory=dict)
    kind: str = field(default_factory=server_kind)
    port: int = 0
    process: object | None = None  # runtime.Server while running
    starts: int = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def db_path(self) -> Path:
        return self.home / "data" / "weir.sqlite3"

    @property
    def logs_dir(self) -> Path:
        return self.home / "contract-logs"

    @property
    def running(self) -> bool:
        server = self.process
        return server is not None and server.process.poll() is None  # type: ignore[attr-defined]

    def environment(self) -> dict[str, str]:
        env = {
            **os.environ,
            "WEIR_HOME": str(self.home),
            "WEIR_SESSION_SECRET": os.environ.get("WEIR_SESSION_SECRET") or DEFAULT_SESSION_SECRET,
            "WEIR_WEB_DIST": str(WEB_DIST),
            # The production limits are per process; a module signs in far more than ten times.
            # The limits themselves are covered by their own contract tests, which lower these.
            "WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS": "10000",
            "WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS": "10000",
            # Quiet by default, like the backend's HTTP tests: no in-process workers, no file-system
            # watcher, and periodic scans that do not queue files. Scenarios turn workers on.
            # Periodic scan *jobs* are still queued for every enabled library with a watched folder
            # (nothing switches the scan timer off any more), so count only the jobs a test caused.
            "WEIR_REFINER_WORKER_COUNT": "0",
            "WEIR_REFINER_WATCHER_ENABLED": "0",
            "WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS": "0",
            "WEIR_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED": "0",
            "WEIR_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_ENABLED": "0",
            "WEIR_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED": "0",
            "WEIR_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED": "0",
        }
        for key in ("WEIR_CORS_ORIGINS", "WEIR_TRUSTED_BROWSER_ORIGINS", "WEIR_ENV"):
            # A developer shell's own settings must not leak into a contract run.
            env.pop(key, None)
        env.update(self.env_overrides)
        return {k: v for k, v in env.items() if v is not None}

    # --- lifecycle ------------------------------------------------------------------------

    def migrate(self) -> None:
        """Bring the database to the current schema without leaving a server running."""

        self.home.mkdir(parents=True, exist_ok=True)
        if self.kind == "python":
            result = subprocess.run(
                [python_executable(), "-m", "alembic", "upgrade", "head"],
                cwd=str(BACKEND_DIR),
                env={**self.environment(), "PYTHONPATH": str(BACKEND_DIR / "src")},
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}")
            return
        self.start()
        self.stop()

    def _command(self) -> tuple[list[str], Path]:
        if self.kind == "python":
            return (
                [
                    python_executable(),
                    "-m",
                    "uvicorn",
                    "weir.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                    "--log-level",
                    "warning",
                ],
                BACKEND_DIR,
            )
        reason = dotnet_unavailable_reason()
        if reason is not None:
            raise RuntimeError(reason)
        exe = (os.environ.get("WEIR_CONTRACT_DOTNET_EXE") or "").strip()
        # The .NET host listens where --host/--port say (ServerListenOptions); it ignores --urls.
        urls = ["--host", "127.0.0.1", "--port", str(self.port)]
        if exe:
            return [exe, *urls], Path(exe).parent
        return ["dotnet", "run", "--project", str(DOTNET_PROJECT), "--no-build", "--", *urls], REPO_ROOT

    def start(self, *, timeout_s: float = 90.0) -> None:
        if self.running:
            return
        if not self.db_path.is_file() and self.kind == "python":
            self.migrate()
        self.port = runtime.pick_free_port()
        command, cwd = self._command()
        env = self.environment()
        env["ASPNETCORE_URLS"] = self.base_url
        if self.kind == "python":
            env["PYTHONPATH"] = str(BACKEND_DIR / "src")
        self.starts += 1
        server = runtime.start_server(
            f"Weir {self.kind} server",
            command,
            cwd=cwd,
            env=env,
            port=self.port,
            url=f"{self.base_url}/health",
            log_path=self.logs_dir / f"server-{self.starts}.log",
        )
        self.process = server
        try:
            runtime.wait_until_up(server, timeout_s=timeout_s)
        except RuntimeError:
            runtime.stop_server(server)
            self.process = None
            raise
        self._wait_ready(timeout_s=timeout_s)

    def _wait_ready(self, *, timeout_s: float) -> None:
        """``/health`` answers before the lifespan finishes on some servers; ``/ready`` is the gate."""

        import httpx

        deadline = time.monotonic() + timeout_s
        last = ""
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"{self.base_url}/ready", timeout=2.0)
                if r.status_code == 200 and r.json().get("ready") is True:
                    return
                last = f"HTTP {r.status_code} {r.text[:200]}"
            except httpx.HTTPError as exc:
                last = repr(exc)
            time.sleep(0.1)
        raise RuntimeError(f"Weir never reported ready at {self.base_url}/ready ({last}).")

    def stop(self) -> None:
        """Graceful stop, then the whole process tree."""

        server = self.process
        if server is not None:
            runtime.stop_server(server)
        self.process = None

    def kill(self) -> None:
        """Hard kill, no shutdown hooks: the "server crashed" case."""

        server = self.process
        if server is None:
            return
        runtime._kill_tree(server.process.pid)  # type: ignore[attr-defined]
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.process.wait(timeout=15)  # type: ignore[attr-defined]
        runtime._forget(server)
        self.process = None

    def restart(self, env_overrides: Mapping[str, str] | None = None) -> None:
        self.stop()
        if env_overrides:
            self.env_overrides.update(env_overrides)
        self.start()

    def log_text(self) -> str:
        parts = []
        for path in sorted(self.logs_dir.glob("server-*.log")):
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(parts)
