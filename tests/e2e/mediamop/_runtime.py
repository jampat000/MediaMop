"""Starting and stopping the servers an E2E run needs, so that runs cannot affect each other (#462).

The suite used to fail intermittently in a full run and pass in isolation. The cause was almost
always an API or Vite process left behind by an earlier aborted run, still holding that run's data
folder, and the symptom arrived three steps later as a mystery sign-in failure. The rules here:

- **Every run gets its own data folder**, even when ``MEDIAMOP_E2E_HOME`` names a parent.
- **Servers are started in their own process group and stopped as a tree**, and every server is
  recorded in a ledger. A later run stops a recorded server that is still answering, so an aborted
  run's leftovers are cleaned up rather than accumulating.
- **A port that already answers is refused** with a message naming it, instead of testing
  against whatever happens to be there.
- **A server that does not come up says so**, with the end of its own log, instead of letting the
  run fail later for a reason nobody can see.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

LEDGER = Path(tempfile.gettempdir()) / "mediamop-e2e-servers.json"
_LOG_TAIL_LINES = 40


@dataclass
class Server:
    name: str
    process: subprocess.Popen[bytes]
    url: str
    log_path: Path


def run_home(explicit_parent: str | None) -> str:
    """A data folder that belongs to this run alone."""

    stamp = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    if explicit_parent:
        home = Path(explicit_parent).expanduser().resolve() / stamp
        home.mkdir(parents=True, exist_ok=False)
        return str(home)
    return tempfile.mkdtemp(prefix=f"mediamop_e2e_{stamp}_")


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def port_answers(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _responds(url: str, timeout_s: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _read_ledger() -> list[dict]:
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_ledger(entries: list[dict]) -> None:
    try:
        LEDGER.write_text(json.dumps(entries), encoding="utf-8")
    except OSError:
        pass


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def reap_leftovers() -> list[str]:
    """Stop servers an earlier run recorded and never stopped. Returns what was stopped.

    A recorded server is stopped only while its recorded address still answers, so a PID the
    operating system has since given to something else is never touched on the PID alone.
    """

    stopped: list[str] = []
    for entry in _read_ledger():
        url = str(entry.get("url") or "")
        pid = int(entry.get("pid") or 0)
        if pid and url and _responds(url):
            _kill_tree(pid)
            stopped.append(f"{entry.get('name')} (pid {pid}, {url})")
    _write_ledger([])
    return stopped


def _record(server: Server) -> None:
    entries = [e for e in _read_ledger() if int(e.get("pid") or 0) != server.process.pid]
    entries.append({"name": server.name, "pid": server.process.pid, "url": server.url})
    _write_ledger(entries)


def _forget(server: Server) -> None:
    _write_ledger([e for e in _read_ledger() if int(e.get("pid") or 0) != server.process.pid])


def log_tail(path: Path, lines: int = _LOG_TAIL_LINES) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no log was written)"
    tail = text.splitlines()[-lines:]
    return "\n".join(tail) if tail else "(the log is empty)"


def start_server(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    port: int,
    url: str,
    log_path: Path,
) -> Server:
    if port_answers(port):
        raise RuntimeError(
            f"Port {port} already has something listening, so the {name} was not started. "
            "Stop the process using it (often a server left behind by an aborted E2E run) and run again."
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "wb")  # noqa: SIM115 - handed to the child, closed when it exits
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(
        list(command), cwd=str(cwd), env=env, stdout=log_file, stderr=subprocess.STDOUT, **kwargs
    )
    server = Server(name=name, process=process, url=url, log_path=log_path)
    _record(server)
    return server


def wait_until_up(server: Server, *, timeout_s: float) -> None:
    """Return once the server answers 200, or raise with a sentence and the end of its log."""

    deadline = time.time() + timeout_s
    last: Exception | None = None
    while time.time() < deadline:
        code = server.process.poll()
        if code is not None:
            raise RuntimeError(
                f"The {server.name} exited (code {code}) before it answered at {server.url}.\n"
                f"Last lines of its log ({server.log_path}):\n{log_tail(server.log_path)}"
            )
        try:
            with urllib.request.urlopen(server.url, timeout=2) as response:
                if response.status == 200:
                    if server.process.poll() is not None:
                        raise RuntimeError(
                            f"Something other than this run's {server.name} answered at {server.url}."
                        )
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        time.sleep(0.25)
    raise RuntimeError(
        f"The {server.name} did not answer at {server.url} within {int(timeout_s)}s ({last!r}).\n"
        f"Last lines of its log ({server.log_path}):\n{log_tail(server.log_path)}"
    )


def stop_server(server: Server, *, timeout_s: float = 8.0) -> None:
    """Stop the server and anything it started; never raises."""

    process = server.process
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                _kill_tree(process.pid)
                process.wait(timeout=timeout_s)
        # A graceful exit can still leave a child behind (Vite, a worker); take the tree down.
        _kill_tree(process.pid)
    except Exception:  # noqa: BLE001 - teardown must finish
        pass
    finally:
        _forget(server)
