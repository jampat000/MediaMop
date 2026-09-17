# Packaging the .NET server (preparation for #523)

This is preparation for [#523](https://github.com/jampat000/Weir/issues/523) (epic
[#514](https://github.com/jampat000/Weir/issues/514), [ADR-0017](adr/ADR-0017-backend-on-dotnet.md)):
it lets you build a Docker image and a Windows Velopack package from the **.NET** server
(`apps/server/src/Weir.Host`) **today**, side by side with the Python packaging that CI and
releases still use. Nothing described here runs in CI yet, and none of the Python packaging
changed:

| Kind | Python (shipped, unchanged) | .NET (this document) |
| --- | --- | --- |
| Docker | `Dockerfile`, `compose.yaml`, `docker/entrypoint.sh` | `docker/server.Dockerfile`, `docker/server.compose.yaml`, `docker/server-entrypoint.sh` |
| Windows | `packaging/windows/build-velopack.ps1`, `packaging/windows/weir-server.spec` | `packaging/windows/build-velopack-server.ps1` |

Both artifacts install/run at `Weir` / `Weir.exe` / port 8788 / `/data/weir` — the same identity
as the Python packaging — because #523 is a switch-over, not a second product.

## Why the .NET server can be packaged before #523 is done

The .NET server does not yet implement every area Refiner needs (see `apps/server/README.md`:
areas are ported one at a time, and "unported job kinds are not claimed"). It already starts,
serves the web app, opens/migrates its SQLite database and answers `/health` and `/ready`, which
is enough to package and smoke-test — just not enough to run the full product yet. Don't read a
green build here as area parity; the contract suite (`tests/contract`) is what proves that.

## Build the Docker image

```bash
docker build -f docker/server.Dockerfile -t weir-dotnet:local .
docker compose -f docker/server.compose.yaml up -d --build
curl -fsS http://localhost:8788/health
```

`docker` was not available in the environment this was prepared in, so the Dockerfile was
validated by careful line-by-line review against `Dockerfile` and `compose.yaml` (matching user,
UID/GID 1000, paths, `WEIR_HOME`/`WEIR_WEB_DIST`/`WEIR_ENV` defaults, port 8788, the `/data/weir`
volume, and the same `/health` healthcheck) rather than by running it. It was not built or run.
Build and smoke it for real before relying on it. Its `dotnet publish` invocation was, however,
proven separately: it uses the same `-p:PublishProfile=<rid>` form that
`build-velopack-server.ps1` was fixed to use below (see "a build gotcha found and fixed here"),
which was verified locally for `win-x64`, `linux-x64` and `linux-arm64` all cross-published from
this Windows environment without errors.

**What's different from `Dockerfile`:**

- **Publish shape.** Self-contained single-file, via `-p:PublishProfile=linux-x64` or
  `linux-arm64` (`apps/server/src/Weir.Host/Properties/PublishProfiles/*.pubxml` — see "a build
  gotcha found and fixed here" below for why it's the profile form and not explicit
  `-r`/`--self-contained`/`-p:PublishSingleFile` flags), matching every other Weir.Host target and
  ADR-0017's publish rule, rather than a framework-dependent publish on the `aspnet` runtime
  image. The final stage is
  `mcr.microsoft.com/dotnet/runtime-deps:10.0-bookworm-slim`: only the native OS dependencies a
  self-contained app needs (libc, OpenSSL — not ICU, since `InvariantGlobalization=true`), no
  second copy of the managed runtime the single-file publish already bundles. This is smaller and
  simpler than shipping the `aspnet` image and is the officially recommended base for
  self-contained deployments.
- **True multi-arch.** `docker/server.Dockerfile` publishes `linux-x64` and `linux-arm64` from a
  single `--platform=$BUILDPLATFORM` SDK stage (cross-publish needs no emulation: only the target
  runtime's NuGet package is downloaded, nothing target-arch is executed). `Dockerfile` today is
  built and published for `linux/amd64` only (`release.yml` lines ~329, ~385); building the
  `.NET` image for `linux/arm64` on an `amd64` GitHub Actions runner still needs QEMU for the
  final stage's `apt-get install` (see CI/release changes below).
- **No separate migration step.** `docker/entrypoint.sh` runs `alembic upgrade head` before
  `exec uvicorn ...`; `Weir.Host` applies its own SQL migrations to the configured database at
  startup (`WeirServer.cs`, `OpenDatabase`), so `docker/server-entrypoint.sh` just execs the
  published binary.
- **No `weir.platform.docker_runtime` yet.** `docker/entrypoint.sh`'s optional Refiner
  path-ownership policy (`WEIR_CHOWN_WATCHED`/`WEIR_CHOWN_TEMP`/`WEIR_CHOWN_OUTPUT`,
  `WEIR_DIR_MODE_*`) calls a Python CLI module that has no .NET port. `docker/server-entrypoint.sh`
  still validates those env vars (so a typo is still caught) but logs a warning and does not apply
  the policy. Tracked as a gap below.
- **Secret generation without Python.** The persisted-`session.secret` fallback in
  `docker/entrypoint.sh` shells out to `python -c "import secrets; ..."`; there is no Python
  interpreter in the `.NET` image, so `docker/server-entrypoint.sh` generates the same 48
  random bytes, base64url-encoded, with coreutils (`head -c 48 /dev/urandom | base64 | tr ...`)
  instead. Same entropy, different tool.

## Build the Windows package

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-velopack-server.ps1
```

Needs the .NET 10 SDK (pinned by `apps/server/global.json`), Node 24, and either an existing
`vpk` global tool matching the `Velopack` package version in `apps/tray/Weir.Tray.csproj`, or
network access for the script to `dotnet tool install`/`update` it (mirrors
`build-velopack.ps1`'s own vpk handling exactly).

**What actually ran, in this environment (2026-09-17):**

- `dotnet build apps/server/Weir.slnx -warnaserror` — 0 warnings, 0 errors.
- The script parses cleanly (`[scriptblock]::Create` gate) and was **run end to end, twice**
  (the first run hit a real build error, described below; the second, after fixing it, completed
  cleanly): web build (`npm ci && npm run build`), FFmpeg download + checksum verify, `dotnet
  publish` of both `Weir.Host` (server, self-contained single-file `win-x64`) and `Weir.Tray`
  (unchanged), the built-in publish smoke test (temp `WEIR_HOME` + the built web dist, an
  `Invoke-RestMethod` `/health` check against the raw published `Weir.exe` before packing),
  pack-directory assembly (the `Weir.exe` → `WeirServer.exe` rename, web-dist and
  `server\bin\ffmpeg\` placement), and `vpk pack`.
- `vpk pack` produced `dist\windows-dotnet\releases\{Weir-win-Setup.exe, Weir-win-Portable.zip,
  Weir-2.6.6-full.nupkg, RELEASES, assets.win.json, releases.win.json}` — a complete, real
  Velopack release, ~215 MB portable/nupkg and ~220 MB setup (self-contained .NET runtime + tray +
  ffmpeg, uncompressed by code signing since no cert was configured locally).
- As one further check beyond the script's own built-in smoke step, the **assembled**
  `dist\windows-dotnet\pack\server\WeirServer.exe` was started directly with `WEIR_HOME` pointed
  at a fresh temp directory and `WEIR_WEB_DIST` pointed at its own sibling `web-dist\` (i.e. the
  exact relative layout the tray app assembles and would launch), and answered both `/health`
  (`{"status":"ok","dependencies":{"database":"ok"}}`) and `--version` (`2.6.6`, matching
  `apps/backend/pyproject.toml`) correctly.
- Every build artifact (`dist/`, `apps/web/dist`, `apps/server/artifacts`,
  `packaging/windows/vendor/ffmpeg`) is gitignored already and was deleted after verification; it
  is not part of this branch.

### A build gotcha found and fixed here (not a product bug)

The first end-to-end run failed at the `.NET server publish` phase with:

```
apps/server/src/Weir.Infrastructure/Runtime/SystemServices.cs(138,47): error IL3000:
'System.Reflection.Assembly.Location.get' always returns an empty string for assemblies
embedded in a single-file app. ...
```

`DetectInstallType` in that file reads `Assembly.Location` **specifically because** it is empty in
a single-file publish — that emptiness is the signal it's testing for, not a mistake — but the
.NET single-file analyzer doesn't know that intent and flags the read as an error under this
repo's `TreatWarningsAsErrors=true`. It reproduced identically for a `linux-x64` cross-publish, so
it would have blocked the Docker image too, not just Windows.

The cause was **how this script (and the first draft of `docker/server.Dockerfile`) invoked
`dotnet publish`**, not the source file: passing `-r <rid> --self-contained true
-p:PublishSingleFile=true ...` as separate command-line switches makes `PublishSingleFile` a
*global* MSBuild property, applied to every project in the build graph — including
`Weir.Infrastructure`, a plain class library that has no reason to run the single-file analyzer at
all. Publishing instead via `-p:PublishProfile=<rid>` (the checked-in
`Weir.Host/Properties/PublishProfiles/*.pubxml`, and the exact command `apps/server/README.md`
already documents) scopes those same properties to the `Weir.Host` project only, which is what the
analyzer actually expects — verified locally for `win-x64`, `linux-x64` and `linux-arm64`, all
clean. Both `build-velopack-server.ps1` and `docker/server.Dockerfile` use the profile form; see
the comments at each `dotnet publish` call. This is flagged in both files so it doesn't regress if
someone "simplifies" the invocation back to explicit flags later.

**What's different from `build-velopack.ps1`:**

- **No PyInstaller, no Python venv.** `dotnet publish apps/server/src/Weir.Host
  -p:PublishProfile=win-x64` (see "a build gotcha found and fixed here" above for why it's the
  profile form and not explicit `-r`/`--self-contained`/`-p:PublishSingleFile` flags) replaces the
  venv bootstrap, `pip install`, and the `weir-server.spec` PyInstaller bundle. The server's
  version comes from the same place either
  way — `apps/backend/pyproject.toml` — but for the .NET build it is read twice over: once by
  this script (to compute `$buildVersion`, exactly as `build-velopack.ps1` does) and once more
  automatically by `apps/server/Directory.Build.props`, which stamps `Weir.Host`'s own assembly
  version from the same file. The script still asserts the two agree (`Weir.exe --version` after
  publish) rather than trusting that silently.
- **A file rename with no tray code change.** `Weir.Host`'s `<AssemblyName>` is `Weir` (see
  `apps/server/src/Weir.Host/Weir.Host.csproj`) — the same name as the tray app's own published
  `Weir.exe`. Copying the server's publish output into the pack directory unchanged would put two
  files named `Weir.exe` in the same package. The script renames the server's copy to
  `WeirServer.exe` inside `packDir\server\`, which is also exactly what
  `apps/tray/Weir.Tray/Program.cs`'s `FindServerExeDirectory()` already looks for — so
  **no tray source change was needed**.
  - `PrepareEnvironment()` in the same file computes `web-dist` as
    `<serverDir>\_internal\web-dist`, falling back to `<serverDir>\web-dist` when the first is
    absent. A `.NET` single-file publish has no `_internal` directory, so the fallback path is
    always the one that's used; the script copies the built web app straight into
    `packDir\server\web-dist`.
  - `WEIR_ALEMBIC_ROOT` (set by the tray only when `<serverDir>\_internal\alembic.ini` exists) is
    simply never set for the .NET server — it doesn't use Alembic, so this is a no-op, not a gap.
- **FFmpeg vendoring is duplicated, not shared, code.** Both scripts download and verify the same
  archive into the same `packaging/windows/vendor/ffmpeg` (gitignored, so running either script
  after the other reuses the checksum-verified copy rather than downloading twice) via an
  `Ensure-WindowsFfmpegRuntime` function that is **copied, not imported** — the two build scripts
  must not depend on each other. Keep them in sync by hand if that function ever changes.
  `build-velopack-server.ps1` copies the two exe's into `packDir\server\bin\ffmpeg\`, matching the
  `<packaged-app-dir>\bin\ffmpeg` candidate that
  `apps/server/src/Weir.Core/Media/MediaToolLocations.cs` already defines.
  - **Known gap:** that resolver (`Weir.Infrastructure.Media.MediaToolResolver`) is not yet
    registered in the server's dependency-injection container (nothing calls
    `AddWeirApi`/`AddWeirJobs` with it, as of this writing) — the ffmpeg/ffprobe layer described in
    `apps/server/README.md` exists and is golden-tested, but nothing in the composition root wires
    it to a real job handler that would call it from a packaged install yet. Vendoring the
    binaries now is forward compatible with that wiring landing later; it does not make ffmpeg
    reachable today. Track this alongside the areas still to be ported (media managers,
    processing engine — epic #514's #520–#522).
- **Output directory.** `dist\windows-dotnet\` instead of `dist\windows\`, so running both
  scripts back to back does not clobber the other's output. `--packId Weir`, `--mainExe Weir.exe`
  and the installer name (`Weir-win-Setup.exe`) are unchanged on purpose: this is preparation for
  the same install identity, not a second app.
- **A lighter smoke test.** `build-velopack-server.ps1` runs its own smoke step directly against
  the freshly published `Weir.exe` (before `vpk pack`): temp `WEIR_HOME`, `WEIR_WEB_DIST` pointing
  at the built web app, then poll `/health`. `scripts/smoke-windows-package.ps1` (used by
  `build-velopack.ps1`) does much more — it logs in, configures a library, enqueues a real
  Refiner pass-through job and checks the byte-identical output — which needs job-handler areas
  the .NET server does not have wired up yet (see the DI gap above). A `.NET` equivalent of that
  full smoke test is one of #523's "proof before deleting" gates, not something this preparation
  can pass yet.

## CI/release changes #523 will need (listed here, **not** applied)

None of these were made. They are the concrete diff #523's "switch over" step will need, based on
reading `.github/workflows/ci.yml` and `.github/workflows/release.yml` as they stand today:

1. **`ci.yml` `docker-smoke` job** — change `docker build -t weir-ci-smoke .` to build
   `docker/server.Dockerfile` (or replace `Dockerfile`'s content once the Python image is
   retired). Add `docker/setup-qemu-action` + `docker/setup-buildx-action` if `linux/arm64` is
   built/tested here too (needed for the final stage's `apt-get install` under emulation — the
   cross-compiling SDK stage itself does not need it). Both new actions must be pinned to a full
   commit SHA (`scripts/check-github-action-pins.mjs` enforces this already).
2. **`ci.yml` `windows-package-smoke` job** —
   - `actions/setup-dotnet` currently installs `dotnet-version: "9.0.x"` for the tray only; add
     `"10.0.x"` (or drop the pin and let `apps/server/global.json`'s `rollForward:
     latestFeature` resolve it) for the server.
   - Replace the `packaging/windows/build-velopack.ps1` call with
     `packaging/windows/build-velopack-server.ps1`.
   - Replace `scripts/smoke-windows-package.ps1` with a .NET-aware equivalent: today's script
     asserts a PyInstaller `_internal` layout (`_internal\web-dist`, `_internal\alembic.ini`,
     `_internal\bin\ffmpeg\...`, a `weir_backend-*.dist-info` folder) that a .NET single-file
     publish does not have, and its full pass-through-job smoke needs the job-handler DI gap
     above closed first.
   - Drop the "Weir web - install and build" / FFmpeg-cache duplication once one script covers
     it (`build-velopack-server.ps1` already builds the web app and vendors ffmpeg itself, same
     as `build-velopack.ps1` does).
3. **`release.yml` `windows-smoke` job** — same three changes as above (dotnet-version,
   `build-velopack-server.ps1`, a .NET-aware smoke script and `-ExpectedVersion`), plus: the
   code-signing and `SHA256SUMS.txt` steps hardcode `dist/windows/releases` — either point them at
   `dist/windows-dotnet/releases` or (once Python packaging is deleted) just drop `-dotnet` from
   this script's output path so it reuses `dist/windows/releases` unchanged.
4. **`release.yml` `publish` job** — both `docker/build-push-action` steps (`file: ./Dockerfile`,
   `platforms: linux/amd64`) need the same two changes as the `docker-smoke` job: build
   `docker/server.Dockerfile` (or the retired-and-replaced `Dockerfile`) and add `linux/arm64` to
   `platforms:` (with QEMU set up, as above). The image labels
   (`org.opencontainers.image.{source,revision,version}`) don't need to change.
5. **Contract suite requirement** — `ci.yml`'s contract-suite matrix already runs a `dotnet`
   backend entry (`continue-on-error: true`, "areas not yet ported report pass/fail... without
   failing the job" — see `ci.yml` around the `contract` job). #523 flips that: the `dotnet`
   backend leg becomes the one that must pass, and the required-check name in the ruleset needs
   to point at it instead of (or in addition to) the `python` leg.
6. **`scripts/check-release-workflow-gates.mjs`** — it currently only asserts that the Docker
   candidate/E2E/smoke gates exist before registry login/publish (see its `docker-smoke` /
   `windows-package-smoke` string checks). It shouldn't need structural changes for a like-for-like
   swap of *which* Dockerfile/script those steps invoke, but re-run it after editing the workflows
   — it is a required gate in this repo (`node scripts/check-release-workflow-gates.mjs`).
7. **Required check names in the GitHub ruleset** — issue #523 flags this explicitly as an
   owner-only change to ask James about (job names change if step 1/2/3 rename or replace jobs
   rather than editing them in place).
8. **`scripts/check-dead-code.mjs`** — issue #523 item 6: this currently only checks Python dead
   code; needs a .NET equivalent (analyzer rule, e.g. an unused-member Roslyn analyzer already
   available via `AnalysisLevel latest-recommended`) or removal, once decided.
9. **Delete the Python-only pieces** once the above are green and the epic's "proof before
   deleting" gates pass (full contract suite, E2E, windows-package-smoke and the Deluno rig, all
   against .NET): `Dockerfile`, `compose.yaml`, `docker/entrypoint.sh`,
   `packaging/windows/build-velopack.ps1`, `packaging/windows/weir-server.spec`, `apps/backend/`,
   and rename `docker/server.*` / `build-velopack-server.ps1` back to the unqualified names (or
   just leave the `-server`/`.server` naming — James's call).

## Files added by this preparation

```
docker/server.Dockerfile
docker/server-entrypoint.sh
docker/server.compose.yaml
packaging/windows/build-velopack-server.ps1
docs/packaging-dotnet.md   (this file)
```

Nothing else changed: `Dockerfile`, `compose.yaml`, `docker/entrypoint.sh`,
`packaging/windows/build-velopack.ps1`, `packaging/windows/weir-server.spec`, and every file under
`.github/workflows/` are byte-for-byte what they were before this branch.
