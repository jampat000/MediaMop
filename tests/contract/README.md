# Weir contract suite

A test suite that judges a **running** Weir server from the outside. It starts the server as its own
process, talks to it only over HTTP, and reads or writes the SQLite file only while the server is
stopped. It never imports `weir`, so the same tests can judge the Python backend today and the .NET
server being ported to (epic #514, this suite is #516, decision record ADR-0017).

## Running it

From the repo root, after the backend is installed and the web app is built (the server serves
`apps/web/dist`):

```bash
cd apps/backend && python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"   # bin/python on Linux
cd apps/web && npm ci && npm run build
# then, from the repo root:
apps/backend/.venv/Scripts/python.exe -m pytest tests/contract -q
```

The suite finds the backend's `.venv` on its own; set `WEIR_CONTRACT_PYTHON` to use another
interpreter (CI sets it to `python`).

Useful options and variables:

| What | How |
| --- | --- |
| Only some areas | `--contract-area auth,system` (repeatable) |
| Only the areas the backend under test must pass | `--contract-required-only` |
| Which server | `WEIR_CONTRACT_SERVER=python` (default) or `dotnet` |
| A published .NET executable instead of `dotnet run` | `WEIR_CONTRACT_DOTNET_EXE=/path/to/Weir.Host` |
| Real ffmpeg for `real_ffmpeg` tests | on `PATH`, or `WEIR_CONTRACT_REAL_FFMPEG_DIR` |
| Separate leftover-server ledger (parallel runs) | `WEIR_CONTRACT_LEDGER=/tmp/ledger.json` |

The end of every run prints a pass/fail line per area.

### Against .NET

`WEIR_CONTRACT_SERVER=dotnet` runs `dotnet run --project apps/server/src/Weir.Host --no-build -- --urls
http://127.0.0.1:<port>` (build it first), or the executable in `WEIR_CONTRACT_DOTNET_EXE`, with the same
environment the Python server gets (`WEIR_HOME`, `WEIR_*` settings, plus `ASPNETCORE_URLS`). The server
must answer `GET /health` and `GET /ready` with `{"ready": true}` once it can take requests, and must
create or migrate its own database on start. Until `apps/server` exists every test is skipped with that
reason.

Areas are listed in [`areas.json`](areas.json). Each has a `required` list: when an area's port issue
is done, add `"dotnet"` to it, and the CI `contract` job's .NET run (`--contract-required-only`) starts
failing on that area instead of only reporting it.

## How it works

- **`conftest.py`** — fixtures. `server` is one server with a fresh `WEIR_HOME` per test module
  (override the module fixture `server_env` for extra environment); `server_factory` makes more, for
  tests that need a clean database or special settings; `client`, `admin` and `client_factory` give
  HTTP clients with their own cookie jars; `fake_ffmpeg`, `fake_managers` and `real_ffmpeg_env` provide
  the outside world. The folder a test lives in is its area and its pytest marker.
- **`support/launcher.py`** — starts, stops, restarts and hard-kills a server. It reuses the E2E
  runtime helpers from `tests/e2e/weir/_runtime.py`: port guard, process-tree teardown, and a ledger
  so a run stops servers an aborted run left behind. The default environment turns off in-process
  workers and periodic enqueue (like the backend's own HTTP tests) and lifts the sign-in rate limits;
  processing scenarios turn workers back on.
- **`support/client.py`** — `WeirClient`, a thin httpx wrapper: CSRF (`post_csrf`, `put_csrf`,
  `delete_csrf`), `bootstrap`, `login`, `ensure_admin`. It returns raw responses.
- **`support/seed.py`** — `with seed.stopped(server) as conn:` stops the server, hands out a sqlite3
  connection, commits and starts the server again. Plain SQL against the shared schema, for rows no API
  creates (a viewer account, an old activity event) and for asserting on rows no API shows.
- **`support/fake_manager.py`** — `FakeManager`, a threaded HTTP server that records every request,
  with presets for Sonarr/Radarr v3 (status, root folders, a scriptable queue with `DELETE`, command,
  manual import) and Deluno (health, manifest with libraries and capabilities, queue, processor events).
- **`support/fake_ffmpeg.py`** and **`support/fake_media_tool.py`** — fake `ffprobe`/`ffmpeg` installed
  into a folder that `WEIR_FFMPEG_DIR` points at. A fixture file written with `fake_media_bytes(probe(...))`
  carries its own ffprobe answer; `set_file_rule("film.mkv", remux_error=..., remux_fail_times=...,
  remux_delay_seconds=..., probe_error=..., integrity_error=...)` scripts failures and slowness; every call
  is logged for assertions (`calls(tool=, step=)`). On Windows the tools are real `.exe` launchers (pip's
  distlib launcher plus a zipped script), because Weir runs them without a shell.
- **`support/polling.py`** — `wait_until`. Tests poll for an outcome with a timeout; they never sleep
  for a fixed time to let something happen.

## Adding a test

1. Put it in the area folder it belongs to (`tests/contract/<area>/test_*.py`); add a new area to
   `areas.json` only for a new port issue.
2. Drive the server only through HTTP. If no API can set up the state you need, seed SQLite while the
   server is stopped; if no API shows the result, read SQLite after stopping it. Never import `weir`
   (collection fails if anything does) and never patch the server.
3. Assert on what a client can observe: status codes, bodies, headers, cookies, files on disk, requests a
   fake manager received, calls the fake ffmpeg received.
4. Use the module `server` when tests can share a database, `server_factory` when they cannot.
5. Wait with `wait_until`/`never_within`, with timeouts that fail with a sentence.
6. When the Python server's behaviour looks wrong, write the test for what it does now and raise a
   separate issue: the contract does not move inside a port (ADR-0017).
7. Lint: `ruff check tests/contract` and `ruff format --check tests/contract` (the backend's rules,
   via `tests/contract/ruff.toml`).
