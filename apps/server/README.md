# Weir server (.NET)

The C# / .NET 10 backend that replaces the Python backend in `apps/backend`, area by area, without changing the HTTP API, the web app or the SQLite schema. Why and how: [ADR-0017](../../docs/adr/ADR-0017-backend-on-dotnet.md). Until the switch (#523), `apps/backend` is the reference and the shipped server.

| Project | Holds |
| --- | --- |
| `src/Weir.Host` | The process: configuration, logging, database startup, Kestrel, Windows Service and systemd support. Builds `Weir` / `Weir.exe`. |
| `src/Weir.Api` | Endpoints and HTTP behaviour (security headers, request ids, serving the web app). |
| `src/Weir.Infrastructure` | SQLite (connections, numbered migrations in `Migrations/`), filesystem, log files. |
| `src/Weir.Core` | Records and rules. No IO. |
| `tests/*` | xUnit tests for each project. |

## Build and test

Needs the .NET 10 SDK (pinned in `global.json`). From the repository root:

```powershell
dotnet build apps/server/Weir.slnx -warnaserror
dotnet test apps/server/Weir.slnx
```

## Run

It reads the same `WEIR_*` environment variables as the Python backend, with the same defaults (see `apps/backend/.env.example`). It does not read `apps/backend/.env`.

```powershell
$env:WEIR_HOME = "$env:TEMP\weir-dotnet"          # optional; defaults to %PROGRAMDATA%\Weir
$env:WEIR_WEB_DIST = "$PWD\apps\web\dist"          # optional; after `npm run build` in apps/web
dotnet run --project apps/server/src/Weir.Host -- --host 127.0.0.1 --port 8788
```

`--port` (what the Windows tray passes) wins over `PORT` (what the Docker entrypoint sets); both default to 8788 on every interface.

On startup the server creates an empty database at the current schema, opens a database already at Alembic head `0036_drop_pruner_tables` without changing it, and refuses anything else with a message. It records its version in Alembic's own `alembic_version` table, so either backend can open a database the other created.

## Schema parity

`tests/Weir.Infrastructure.Tests/schema/alembic-head.sql` is the schema and seed rows that `alembic upgrade head` creates. The parity test builds a database from it and one from the .NET migrations and compares tables, columns, types, defaults, keys, indexes, foreign keys, SQL text and rows. After an Alembic change, regenerate it with the backend's virtualenv:

```powershell
apps/backend/.venv/Scripts/python.exe scripts/dump-alembic-schema.py          # write
apps/backend/.venv/Scripts/python.exe scripts/dump-alembic-schema.py --check  # CI runs this
```

## Rules parity

`Weir.Core.Rules` is a port of Refiner's rules engine (`refiner_remux_rules.py`, `refiner_track_sorters.py`, `refiner_metadata_rules.py`, the pure parts of `refiner_original_language.py` and the display helpers). `tests/Weir.Core.Tests/Rules/golden/*.json` hold ffprobe-style inputs with the plan, notes and display lines the Python engine produced for them; `GoldenParityTests` requires the same answers. After a change to those Python modules, regenerate them with the backend's virtualenv:

```powershell
apps/backend/.venv/Scripts/python.exe scripts/generate-rules-golden.py          # write
apps/backend/.venv/Scripts/python.exe scripts/generate-rules-golden.py --check  # compare only
```

### Golden overrides (deliberate divergence from Python)

Issue #537 fixed defects in the rules engine that the golden corpus had pinned as "today's behaviour" (its items 1, 2, 3, 5 and 6 — see the issue for each one). `apps/backend` is being retired (ADR-0017) and is not touched to "fix" these in Python, so regenerating the golden files from Python would just re-record the same bugs. Instead, a case whose correct answer now differs from Python's recorded one gets a same-named file in `tests/Weir.Core.Tests/Rules/golden/overrides/`, holding the issue number, which item(s) of it, and the new expected output, e.g.:

```json
{
  "issue": 537,
  "items": [1, 5],
  "expected": { "...": "the plan the fixed engine actually produces" }
}
```

`GoldenParityTests` reads this instead of the original file's `expected` for that one case; every other case is still compared against Python's recorded output, byte for byte. `sorters.json` holds several cases in one file, so its override has the same shape plus a `cases` list of `{"index": N, "expected": {...}}` keyed by position in that file's `cases` array, overriding only the cases named in it. `Every_override_names_a_real_golden_case` guards against a stale or misnamed override file.

### Known rules-engine gaps

- **Issue #537 item 4 (prefer the original language) is not wired up.** `RefinerRulesConfig.PreferredAudioIndices` and `OriginalLanguageNote` already flow straight into `RemuxRules.PlanRemux` unchanged, and `RefinerRulesConfig.WithOriginalLanguage(OriginalLanguageOutcome)` lets a caller copy an `OriginalLanguage.SelectTracks` decision into a config in one call. What is missing is the remux pass itself calling that lookup — it needs the manager/TMDb metadata lookup from #520, which is not ported yet. The item stays open until a contract scenario proves a manager's original language actually decides the kept audio track end to end.
- **Issue #495 (track flags from names) is engine-only so far.** `Weir.Core.Rules.TrackFlagsReader.Detect` and the new `RefinerRulesConfig.RemoveHearingImpairedSubs` field are wired into `RemuxRules.PlanRemux` (subtitle forced/hearing-impaired handling, audio commentary/dub/audio-description). Persisting the new setting, exposing it over the API, and the web checkbox are not in scope here — they wait on the settings/refiner-config API port that is already in flight.

## ffmpeg parity

`Weir.Core.Media` ports the decisions in `refiner_remux_mux.py` and `refiner_hardware_acceleration.py`: ffprobe and ffmpeg command lines (token for token), unreadable-media classification, output and duration validation, progress parsing and hardware choice. `Weir.Infrastructure.Media.MediaTools` runs the tools through `IProcessRunner` (`ProcessRunner` kills the whole process tree on timeout or cancellation). `tests/Weir.Core.Tests/Media/golden/*.json` record what the Python functions did with their processes replaced by recorded inputs, including log payloads and exception messages; `MediaGoldenParityTests` and `MediaToolsGoldenTests` require the same. Regenerate after a change to those Python modules:

```powershell
apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py          # write
apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py --check  # compare only
```

`RealFfmpegTests` run real ffprobe and ffmpeg on files generated with `-f lavfi`. They skip unless the tools are found through `WEIR_FFMPEG_DIR` or `PATH`; on Windows, point `WEIR_FFMPEG_DIR` at a packaged build's `_internal/bin/ffmpeg`.

### Deliberate divergences from the golden fixtures

Golden parity pins today's Python behaviour, bugs included. Fixing one of those bugs (#539) makes the .NET port behave differently from the Python code the golden fixtures were captured from on purpose, so regenerating the fixtures from Python would erase the fix instead of proving it. Where a case's expected value changed for this reason, the fixture stays as Python produced it and the test that reads it patches the loaded expectation instead — a small `GoldenDivergences` helper next to each affected test class (`Weir.Core.Tests.Media.MediaGoldenParityTests` and `Weir.Infrastructure.Tests.Media.MediaToolsGoldenTests`), named for the GitHub issue that required it. Every case the fix does not touch still runs against the unmodified fixture, so the suite keeps proving parity everywhere it still holds. #539 item 1 is the current entry: ffprobe now runs with `-v error` instead of the fixture's `-v quiet`, which changes the recorded argv and the `REFERENCE_FFPROBE_CALL` log line (and, for a probe timeout, the `Command '[...]' timed out` message) but nothing else in either fixture.

Fixed in #539, real ffmpeg tested (`RealFfmpegTests`) and documented here:

1. **Unreadable media on real files.** ffprobe ran with `-v quiet`, so its diagnostics never reached stderr and `MediaUnreadableException` could never fire outside of scripted tests. It now runs with `-v error` (`FfmpegCommands.BuildFfprobeArgv`); verbosity does not affect `-print_format json`, so stdout is unchanged. A zero-filled `.mkv` (the exact repro in #494) is now classified unreadable.
2. **Hardware acceleration reaching the executed command.** `MediaTools.RemuxToTempFileAsync` built its own argv for `RunFfmpegAsync` without the caller's decided acceleration flags, so a library configured for hardware decoding always ran in software. `RemuxToTempFileAsync(..., acceleration:)` now threads an `AccelerationDecision` into the same `FfmpegCommands.BuildRemuxArgv` call used for both the debug-log summary and the executed argv, so the two can no longer diverge.
3. **Truncated Matroska passing validation.** A Matroska file cut in half keeps its full header duration, so `ValidateRemuxOutputAsync`'s duration check passes it; `ValidateMediaIntegrityAsync`'s full demux also exited 0 on this ffmpeg build, only warning `File ended prematurely`. It now fails when that exit-0 read carries a marker in `ProbeOutput.IntegrityIncompleteMarkers` (`"file ended prematurely"`, `"truncating packet"`, `"partial file"`), and — where practical, i.e. whenever ffmpeg reported at least one timestamp — when the last decoded timestamp (`-progress pipe:1`, reused on this read) falls short of the probed duration by more than the same tolerance `ValidateRemuxOutput` uses.
4. **A silent progress run never timing out.** The reference's progress loop only checks its timeout as a line arrives, so a process stuck reading its input (and so never writing a line) hangs forever. `ProcessRunner`'s timeout is a wall-clock timer, independent of stdout activity, so this was already fixed by the port; `ProcessRunnerTests.A_progress_run_that_never_writes_a_line_is_still_stopped_by_the_timer` and `RealFfmpegTests.A_progress_run_that_never_writes_a_line_is_still_stopped_by_the_timer` (a real ffmpeg blocked on an unconnected named pipe) keep it proven.
5. **Smaller decisions, recorded and tested:**
   - The `"end of file"` unreadable-media marker is narrowed: ffmpeg's own `av_strerror` text for a plain `AVERROR_EOF` is the bare phrase "End of file", which still means the content is bad, but the same underlying error qualified as `"premature end of file"` or `"unexpected end of file"` is ffmpeg's wording for a truncated or still-downloading file — a completeness problem, not evidence the content itself is unreadable — so those two phrasings are excluded (`ProbeOutput.FailureFor`).
   - A plain (non-progress) ffmpeg timeout raises `MediaToolTimeoutException`, the same classified error probing uses, instead of leaking `subprocess.TimeoutExpired` uncaught as the reference does.
   - A timeout, in either ffmpeg mode, kills the whole process tree, not just the direct child — some hwaccel and filter setups spawn helpers that would otherwise survive and keep the output file open.
   - Hardware detection decodes `ffmpeg -hwaccels`' output as UTF-8 with replacement (`ProbeOutput.CapturedText`), like every other tool output this layer reads, instead of the reference's locale encoding.
   - The integrity check runs on every platform. The reference skips it on Windows (`if os.name != "nt"` in `file_remux_pass/run.py`), reasoning that Windows write handles are exclusive so a reader can never see a half-written file; that does not hold for every way Weir sees a file arrive on Windows (SMB shares, WSL2 bind mounts, downloaders that preallocate then write), and #494 was itself filed against a Windows rig. `MediaTools.ValidateMediaIntegrityAsync` makes no platform distinction; a future caller should not reintroduce one without a concrete, current reason to.

## Jobs and workers

The durable queue is the Python backend's `refiner_jobs` table, used the same way: the same statuses, dedupe keys, claim statement, lease checks, retry backoff and failure wording, and the same timestamp text, so either backend can claim, finish or recover a row the other wrote (`tests/Weir.Infrastructure.Tests/Jobs/CrossBackendTests.cs` proves it against the Python code when `apps/backend/.venv` exists, or `WEIR_TEST_PYTHON` names an interpreter with the backend's dependencies; the cross-checks always import this checkout's `apps/backend/src`).

- `Weir.Core/Jobs`: the rules (job kind guard, admission, schedule grid, backoff, failure wording, recovery wording, Weir's temp file names).
- `Weir.Infrastructure/Jobs`: `RefinerJobStore` (SQLite), `RefinerJobProcessor` (one worker pass), startup recovery, history retention, periodic enqueue and the hosted services. `AddWeirJobs` registers all of it.
- Shared by every area: `Weir.Core/Activity` (the event types, `ActivityClassifier` and `IActivityWriter`, with the one insert in `Weir.Infrastructure/Activity/SqliteActivityWriter`), `Weir.Core/Observability` (operator failure wording), `Weir.Core/Json/PyStrings` (Python `str` slicing, `strip()` and `repr()`), `Weir.Core/Time` (`PyDateTime`, IANA `TimeZones`) and `AddWeirPlatform` (the shared singletons).
- Periodic work (`IPeriodicTask`: session cleanup, log retention, configuration backup, history retention) runs in `PeriodicTaskService` with the Python loops' timing: run at start or after one interval, then every interval, with a shorter cooldown after a failure where Python has one. It starts after startup recovery.
- Job handlers implement `IJobHandler` and are registered as singletons by the area that ports them.

**Unported job kinds are not claimed.** Python's worker claims every eligible row and fails any kind it has no handler for. While handlers are still being ported, a .NET worker doing that would fail real work, so it claims only kinds with a registered handler, plus retired or unprefixed kinds, which it claims only to refuse with Python's wording. Everything else stays `pending` for a backend that can run it. Periodic families are timed only when their kind has a handler, for the same reason.

Startup recovery also fixes #534: besides requeuing leased rows and removing `.partial` outputs, it removes the remux temp output of interrupted jobs, and any other remux temp output at the top of a library work folder. Only Weir's exact temp names (`{stem}.refiner.XXXXXXXX{suffix}` and the dry-run placeholder) are ever deleted.

## Activity

`Weir.Api/Endpoints/ActivityEndpoints` ports `weir.platform.activity.router`: `recent` (filters, `before_id` paging), `export` (CSV and JSON), `file-history` and its removal, and the `stream` of `activity.latest` frames. The SQL in `Weir.Infrastructure/Activity/ActivityHistoryStore` is the text SQLAlchemy compiles, so rows that tie on `created_at` come back in the same order; `ActivityHistoryStoreTests` compares the response and export bytes with the Python router on one database. Python quirks kept on purpose: with no filter the `total` is the page size (the count loses its `FROM`), and `file-history` removal deletes processing records for the path without the library's null fallback that Activity events get.

Writers never notify listeners directly. `SqliteActivityWriter` records the ids it wrote on the unit of work or raw transaction, and `ActivityNotifications` tells the database's `ActivityLatestNotifier` after the commit (a rollback tells nobody). Code that commits its own raw transaction after `SqliteActivityWriter.Record` calls `ActivityNotifications.TransactionCommitted`, as `RefinerJobStore.InTransactionAsync` does. `RefinerFileLogRetentionTask` prunes processing records hourly by `file_log_retention_days`.

## Publish

Self-contained single-file builds for `win-x64`, `linux-x64` and `linux-arm64`:

```powershell
dotnet publish apps/server/src/Weir.Host -r win-x64 -o apps/server/artifacts/publish/win-x64
dotnet publish apps/server/src/Weir.Host -p:PublishProfile=linux-arm64
```
