"""Start, stop, restart and kill the Weir server under test.

The suite never imports Weir. It starts the server as a separate process, talks to it over HTTP,
and reads the SQLite file only while the server is stopped. The server is the .NET server
(``WEIR_CONTRACT_SERVER=dotnet``, the only kind): ``dotnet run --project apps/server/src/Weir.Host --no-build --
--host 127.0.0.1 --port N``, or the published executable named by ``WEIR_CONTRACT_DOTNET_EXE``. It owns its
own migrations, so "migrate" means one start-and-stop.

Process-tree teardown, the port guard, and the ledger that reaps servers an aborted run left
behind all come from the E2E runtime helpers (#462). The contract suite keeps its own ledger file
(``WEIR_CONTRACT_LEDGER`` overrides it) so an E2E run and a contract run never stop each other's
servers.
"""

from __future__ import annotations

import contextlib
import hashlib
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
WEB_DIST = REPO_ROOT / "apps" / "web" / "dist"
DOTNET_PROJECT = REPO_ROOT / "apps" / "server" / "src" / "Weir.Host"

DEFAULT_SESSION_SECRET = "contract-suite-session-secret-at-least-32-chars"
# The kinds of server the suite can judge. The Python backend was retired in #523.
SERVER_KINDS = ("dotnet",)


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
    module.LEDGER = Path(ledger) if ledger else Path(tempfile.gettempdir()) / _default_ledger_name()
    return module


def _default_ledger_name() -> str:
    """Per-checkout ledger filename: several worktrees on one machine (parallel agents, each with its
    own clone of this repo) must not reap each other's contract servers through one shared ledger file,
    so the default path is salted with a short hash of this checkout's root."""

    checksum = hashlib.sha1(str(REPO_ROOT.resolve()).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"weir-contract-servers-{checksum}.json"


runtime = _load_runtime()


def server_kind() -> str:
    kind = (os.environ.get("WEIR_CONTRACT_SERVER") or "dotnet").strip().lower()
    if kind not in SERVER_KINDS:
        raise RuntimeError(f"WEIR_CONTRACT_SERVER must be one of {', '.join(SERVER_KINDS)}; got {kind!r}.")
    return kind


def dotnet_unavailable_reason() -> str | None:
    """Why the .NET server cannot be started here, or None when it can."""

    exe = (os.environ.get("WEIR_CONTRACT_DOTNET_EXE") or "").strip()
    if exe:
        return None if Path(exe).is_file() else f"WEIR_CONTRACT_DOTNET_EXE points at {exe}, which does not exist."
    if not DOTNET_PROJECT.is_dir():
        return f"The .NET server project {DOTNET_PROJECT.relative_to(REPO_ROOT)} does not exist."
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
            # Quiet by default: no in-process workers, no file-system
            # watcher, and periodic scans that do not queue files. Scenarios turn workers on.
            # Periodic scan *jobs* are still queued for every enabled library with a watched folder by
            # default here (this env block does not set the switch below), so count only the jobs a
            # test caused, or pass WEIR_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED=0
            # to turn the timer off outright (#533; asserted in
            # tests/contract/jobs/test_watched_folder_scan_schedule_toggle.py).
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
        self.start()
        self.stop()

    def _command(self) -> tuple[list[str], Path]:
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
        self.port = runtime.pick_free_port()
        command, cwd = self._command()
        env = self.environment()
        env["ASPNETCORE_URLS"] = self.base_url
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
