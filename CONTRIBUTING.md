# Contributing - Weir

Weir is a self-hosted media workflow app with a C# / .NET 10 server and SQLite in `apps/server`, a React + Vite web shell in `apps/web`, and a .NET Windows tray app in `apps/tray`.

## Workflow

Use short-lived branches and open pull requests into `main`. Keep CI green before merge.

## Local checks

Server build and unit tests. Needs the .NET 10 SDK (pinned in `apps/server/global.json`). Warnings are errors, including the unused-code analyzers.

```powershell
dotnet build apps/server/Weir.slnx -warnaserror
dotnet test apps/server/Weir.slnx
```

`RealFfmpegTests` skip unless ffmpeg and ffprobe are on `PATH` or `WEIR_FFMPEG_DIR` names a folder holding them. Dependency advisories: `node scripts/check-dotnet-vulnerabilities.mjs apps/server/Weir.slnx`.

Web checks. `package-lock.json` is committed, so prefer reproducible installs.

```powershell
cd apps/web
npm ci
npm run lint
npm run format
npm run api:types:check
npm run build
npm run test
cd ../..
node scripts/check-dead-code.mjs
```

The contract suite and the E2E smoke are Python test runners that judge a running .NET server from outside. Install their locked dependencies once (Python 3.11+):

```powershell
python -m pip install --require-hashes -r tests/requirements.txt
python -m playwright install chromium
```

Contract suite (every area is required on .NET; see [`tests/contract/README.md`](tests/contract/README.md)):

```powershell
dotnet build apps/server/Weir.slnx
cd apps/web; npm ci; npm run build; cd ../..
python -m pytest tests/contract -q --contract-required-only
```

E2E smoke (a temporary SQLite home, Playwright Chromium, the built web app served by the .NET server):

```powershell
dotnet build apps/server/Weir.slnx
cd apps/web; npm ci; npm run build; cd ../..
$env:WEIR_E2E = "1"
$env:WEIR_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
python -m pytest tests/e2e/weir -q --tb=short
```

Windows package: `powershell -ExecutionPolicy Bypass -File packaging/windows/build-velopack.ps1`, then `powershell -ExecutionPolicy Bypass -File scripts/smoke-windows-package.ps1`.

See `docs/local-development.md` for env layout and CI parity.

Remote Docker validation does not require local Docker Desktop:

```powershell
.\scripts\verify-docker-remote.ps1
```

This triggers the GitHub `Test` workflow for the current ref and watches it. The Docker build and smoke test run on GitHub-hosted runners.

## Security

Do not commit `.env`, real secrets, production database files, logs, backups, or machine-specific media paths. Use `.env.example` patterns only.

## License

By contributing to Weir, you agree that your contribution is provided under the repository license: AGPL-3.0-or-later.
