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

## ffmpeg parity

`Weir.Core.Media` ports the decisions in `refiner_remux_mux.py` and `refiner_hardware_acceleration.py`: ffprobe and ffmpeg command lines (token for token), unreadable-media classification, output and duration validation, progress parsing and hardware choice. `Weir.Infrastructure.Media.MediaTools` runs the tools through `IProcessRunner` (`ProcessRunner` kills the whole process tree on timeout or cancellation). `tests/Weir.Core.Tests/Media/golden/*.json` record what the Python functions did with their processes replaced by recorded inputs, including log payloads and exception messages; `MediaGoldenParityTests` and `MediaToolsGoldenTests` require the same. Regenerate after a change to those Python modules:

```powershell
apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py          # write
apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py --check  # compare only
```

`RealFfmpegTests` run real ffprobe and ffmpeg on files generated with `-f lavfi`. They skip unless the tools are found through `WEIR_FFMPEG_DIR` or `PATH`; on Windows, point `WEIR_FFMPEG_DIR` at a packaged build's `_internal/bin/ffmpeg`.

## Publish

Self-contained single-file builds for `win-x64`, `linux-x64` and `linux-arm64`:

```powershell
dotnet publish apps/server/src/Weir.Host -r win-x64 -o apps/server/artifacts/publish/win-x64
dotnet publish apps/server/src/Weir.Host -p:PublishProfile=linux-arm64
```
