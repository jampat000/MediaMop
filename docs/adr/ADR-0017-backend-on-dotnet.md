# ADR-0017: Weir's backend moves to C# on .NET 10

- **Status:** Accepted
- **Date:** 2026-09-17
- **Decided by:** James

## Context

Weir started as Weir, a Python (FastAPI, SQLAlchemy, Alembic) backend with a React + TypeScript web app. The product has since narrowed to one job: a processing stage between a media manager's completed downloads and its import, and soon also its library (library mode, #505). It is **Windows first**, with Linux and Docker as full targets.

The rename to Weir (#458) was already a reset: no installs, no compatibility promises. That made it the one cheap moment to ask whether the stack is the right one, independent of what exists.

What Weir needs from a stack:

1. Ships well on Windows (installer, tray, auto-update), Linux, Docker and ARM64 NAS devices.
2. Small and quiet as a 24/7 service.
3. Reliable long-running work: a durable queue, ffmpeg subprocesses, careful filesystem work (hardlinks, atomic renames, Windows sharing violations, crash recovery), schedules, folder watching.
4. A clean HTTP API: webhooks, outbound calls to Sonarr/Radarr/Deluno, SQLite, auth and CSRF, live updates.
5. **Catching mistakes before they ship.** A wrong move here loses someone's media.
6. Maintainable for years.

Raw speed isn't on the list: ffmpeg does the heavy lifting in every option.

## Options considered

| | Python (current) | **C# / .NET 10** | Go | Rust | TypeScript (Node/Bun) |
|---|---|---|---|---|---|
| Windows-first distribution | PyInstaller: large, slow start, antivirus false positives | **Velopack native, tray and Windows Service first-class, single-file publish** | Good single binary; the tray and installer need more work | Good binary; more work | Newer, less proven |
| Linux, Docker, ARM64 | Works, heavy | Self-contained single-file for linux-x64/arm64; small official images | Best | Very good | OK |
| Idle memory | High | Medium | Lowest-but-one | Lowest | Medium-high |
| Catching bugs at compile time | Weakest (types are an add-on check) | **Very good**: nullable as errors, records, pattern matching, analyzers | Good, without exhaustive modelling | Best | Medium, not enforced at runtime |
| Modelling complex rules | Good | **Very good** | Verbose | Very good | Good |
| Feature speed | Fastest | Fast | Fast | Slowest | Fast |
| Long-term stability | Dependency churn | Good (yearly release, LTS) | Strongest | Good | Most churn |

## Decision

**C# on .NET 10** for the backend. The web app stays **React + TypeScript + Vite + TanStack Query + Tailwind**.

Why not Go: its standout advantage (easy cross-platform single binaries) is mostly matched by .NET 10. What's left (tens of MB of idle memory, a smaller image) doesn't matter on the hardware Weir runs on. Its weaker bug-catching does matter, and so does .NET's clearly better Windows-first story.

Why not Rust: the best correctness, but every feature is slower to build, for a product whose heavy work is ffmpeg.

Why not stay on Python: the weakest fit for a Windows-first self-hosted daemon, and the weakest at catching mistakes before they ship.

Deluno also being .NET was deliberately **not** a factor. It's a bonus: one team skill set, and shared conventions.

The frontend stays because React + TypeScript is already the modern standard choice, it's lean (six runtime dependencies), and a rewrite would buy nothing.

## How we port without gambling

1. **The contract doesn't move.** The HTTP API (paths, bodies, status codes, cookies, CSRF), the web app and the SQLite schema stay as they are, so the React app and a test database work against either backend.
2. **Parity is proven, not asserted.** A language-neutral **contract suite** drives a running server only over HTTP (plus seeding through the API or the database file), and the E2E suite runs against it. Both must pass against Python first, then against .NET.
3. **Area by area.** Each area is done when its contract tests pass on .NET. The hard-won edge cases (settling detection, source fingerprinting, output validation, failure policy, reject, hand-off ledger, crash recovery) move with their tests.
4. **Switch and retire.** When .NET passes everything, including E2E, the packaged smoke tests and the Deluno rig, packaging and CI move to .NET and the Python backend is deleted in one PR.
5. **Features wait.** Library mode (#505–#509) and the track-rule work (#495–#498, #500–#503) are built once, in C#, after the switch.

## Engineering rules for the C# backend

- `.NET 10` (SDK pinned in `global.json`), `Nullable` enabled with nullable warnings as **errors**, `TreatWarningsAsErrors`, latest analyzers (`AnalysisLevel latest-recommended`), `EnforceCodeStyleInBuild`.
- ASP.NET Core minimal APIs; `System.Text.Json` source generation where practical.
- SQLite through `Microsoft.Data.Sqlite` with explicit SQL in typed repositories, and numbered SQL migrations that reproduce the current schema exactly. This matches Deluno, keeps queries visible, and stays trimming/AOT friendly.
- Immutable `record` types for plans, rules and results; sealed hierarchies with `switch` expressions for outcomes and failure kinds.
- `TimeProvider` for time, `IFileSystem`-style seams for the filesystem work that needs fault injection (the swap).
- Tests: xUnit, with unit tests next to each area plus the shared contract suite. Every gate runs in CI.
- Publish: self-contained single-file for `win-x64`, `linux-x64`, `linux-arm64`; Docker image built from the Linux publish plus ffmpeg; Velopack for Windows.

## Consequences

- Feature work pauses until the switch.
- For a while the repo holds two backends. The Python one only receives fixes needed to keep the contract suite honest.
- Contributors need .NET 10 instead of Python.
- Amends: ADR-0007 (worker lanes, already collapsed) and the packaging notes in ADR-0016. Their decisions carry over; the implementation language changes.

## Update (2026-09-17): the switch is done (#523)

The .NET server passed the full contract suite, E2E and the packaged Windows smoke, and #523 switched over:

- The Docker image (`Dockerfile`, now `linux/amd64` and `linux/arm64`) and the Windows Velopack package (`packaging/windows/build-velopack.ps1`) run the .NET server. CI's required checks (`weir`, `docker-smoke`, `windows-package-smoke`) build, test and package .NET; the contract suite runs against .NET only, with every area required.
- `apps/backend` and every Python-only script, lock file and tool configuration are deleted. Python remains only as the interpreter for the outside test runners (`tests/contract`, `tests/e2e`, `scripts/live-packaged-e2e.py`), pinned in `tests/requirements.txt`; they judge the server over HTTP and never import it.
- **The schema freeze is lifted.** The .NET migrations in `apps/server/src/Weir.Infrastructure/Migrations` are now the only source of the SQLite schema, and the next migration may diverge from the old Alembic head `0036_drop_pruner_tables`. The checked-in `alembic-head.sql` stays as a frozen reference for the baseline; nothing regenerates it. The golden rules and ffmpeg fixtures are likewise maintained by hand as .NET test fixtures now.
- The product version moved from `apps/backend/pyproject.toml` to `WeirVersion` in `apps/server/Directory.Build.props`.
- Not ported yet, and tracked separately: the filesystem watcher (new files are found by the periodic scan only) and Processing library discovery/unlink (`OpenApiDocumentParityTests.KnownGaps`).
- Features that waited on the switch (library mode #505–#509, track rules #495–#498, #500–#503) are built in C# from here.
