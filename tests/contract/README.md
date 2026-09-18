# Weir contract suite

A test suite that judges a **running** Weir server from the outside. It starts the server as its own
process, talks to it only over HTTP, and reads or writes the SQLite file only while the server is
stopped. It never imports Weir. It was written against the Python backend and proved the .NET server
matched it area by area (epic #514, this suite is #516, decision record ADR-0017); since the switch
(#523) it judges the .NET server only, and every area in `areas.json` is required.

## Running it

From the repo root. The suite is written in Python, so it needs a Python 3.11+ interpreter with the
locked runner dependencies, the .NET 10 SDK to build the server, and the built web app (the server
serves `apps/web/dist`):

```bash
python -m pip install --require-hashes -r tests/requirements.txt
dotnet build apps/server/Weir.slnx
cd apps/web && npm ci && npm run build && cd ../..
python -m pytest tests/contract -q --contract-required-only
```

Useful options and variables:

| What | How |
| --- | --- |
| Only some areas | `--contract-area auth,system` (repeatable) |
| Only the areas the server under test must pass | `--contract-required-only` |
| Which server | `WEIR_CONTRACT_SERVER=dotnet` (the default and only kind) |
| A published .NET executable instead of `dotnet run` | `WEIR_CONTRACT_DOTNET_EXE=/path/to/Weir` |
| Real ffmpeg for `real_ffmpeg` tests | on `PATH`, or `WEIR_CONTRACT_REAL_FFMPEG_DIR` |
| Separate leftover-server ledger (parallel runs) | `WEIR_CONTRACT_LEDGER=/tmp/ledger.json` |

Without `WEIR_CONTRACT_LEDGER`, the default ledger path already includes a short hash of the checkout's
own root (`weir-contract-servers-<hash>.json` in the OS temp dir), so two worktrees of this repo on one
machine (parallel agents, say) get separate ledgers and never reap each other's contract servers.

The end of every run prints a pass/fail line per area.

### The server under test

The suite runs `dotnet run --project apps/server/src/Weir.Host --no-build -- --host 127.0.0.1 --port <port>`
(build it first), or the executable in `WEIR_CONTRACT_DOTNET_EXE`, with a fresh `WEIR_HOME`, the `WEIR_*`
settings below, and `ASPNETCORE_URLS`. The server must answer `GET /health` and `GET /ready` with
`{"ready": true}` once it can take requests, and must create or migrate its own database on start.

A test that describes behaviour only some server kinds have on purpose is marked with the kinds it
applies to, and is skipped with the reason on the others (with a single kind this is rarely needed):

```python
@pytest.mark.backends("dotnet", reason="...the ADR or issue that decided it...")
def test_something_only_one_kind_does(...): ...
```

Use it only for a decision recorded in an ADR or issue, never to hide unfinished work.

### Known bugs: proving a fix, not just describing today

Some contract tests currently assert today's *buggy* behaviour so the suite stays green (the README
entry for the bug says so, and points at the correct-behaviour test). For a filed issue whose fix is
still pending, add a **separate** test that asserts the *correct* behaviour and mark it
`known_bug`, which applies `pytest.xfail(strict=True)` on the listed backends:

```python
@pytest.mark.known_bug(issue=530)
def test_files_lists_passed_through_and_rejected_rows(...): ...
```

- `issue` is the GitHub issue number; `backends` (default: every server kind) lists which servers still
  get it wrong.
- `strict=True` is automatic: once the fix lands, the test unexpectedly **passes** (XPASS),
  which `strict` turns into a failure. That failure is the signal to delete the `known_bug` marker —
  the test then just asserts correct behaviour like any other.
- Leave the old test that asserts today's behaviour in place with a comment pointing at the issue and
  the new test, so both the workaround and the fix are visible until the marker comes off.

Areas are listed in [`areas.json`](areas.json). Each has a `required` list of server kinds that must
pass it; CI's `contract` job runs exactly those (`--contract-required-only`). Every area requires `dotnet`.

## How it works

- **`conftest.py`** — fixtures. `server` is one server with a fresh `WEIR_HOME` per test module
  (override the module fixture `server_env` for extra environment); `server_factory` makes more, for
  tests that need a clean database or special settings; `client`, `admin` and `client_factory` give
  HTTP clients with their own cookie jars; `fake_ffmpeg`, `fake_managers` and `real_ffmpeg_env` provide
  the outside world. The folder a test lives in is its area and its pytest marker.
- **`support/launcher.py`** — starts, stops, restarts and hard-kills a server. It reuses the E2E
  runtime helpers from `tests/e2e/weir/_runtime.py`: port guard, process-tree teardown, and a ledger
  so a run stops servers an aborted run left behind. The default environment turns off in-process
  workers and periodic enqueue and lifts the sign-in rate limits;
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
6. When the server's behaviour looks wrong, write the correct-behaviour test with a `known_bug` marker
   and raise an issue for the fix, rather than asserting the bug.
7. Lint: `ruff check tests/contract` and `ruff format --check tests/contract` (rules in
   `tests/contract/ruff.toml`; `ruff` comes with `tests/requirements.txt`).
