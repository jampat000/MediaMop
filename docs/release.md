# Weir releases

Weir now ships three release deliverables from a tagged release:

1. a GitHub Release for the tagged source snapshot
2. a Windows desktop package (Velopack installer + delta update files)
3. a Docker image published to GitHub Container Registry

The Windows artifact is a desktop app with a .NET tray host and Velopack for delta updates. It is not a Windows service.

Weir is released under AGPL-3.0-or-later. Release artifacts are built from the tagged source tree and remain subject to that license.

## Contract

1. Update the version in both files in a normal PR:
   - `<WeirVersion>` in `apps/server/Directory.Build.props`
   - `version` in `apps/web/package.json`

   The release workflow checks that the tag `vX.Y.Z` matches both and stops if either differs.
2. Merge to `main` after `Test / weir` passes.
3. Create user-facing release notes for the target tag before pushing it:

   - Create `docs/release-notes/vX.Y.Z.md` using `docs/release-notes/TEMPLATE.md`.
   - Keep wording operator-friendly and focused on what changed for users.

4. Create an annotated tag on the merge commit:

   ```bash
   git fetch origin
   git checkout main
   git pull origin main
   git tag -a vX.Y.Z -m "Weir vX.Y.Z"
   git push origin vX.Y.Z
   ```

5. Pushing `v*` triggers `.github/workflows/release.yml`.
6. The release workflow requires `docs/release-notes/vX.Y.Z.md` for the tag and publishes that file as the GitHub Release body.

Local Docker is not required for this release path. Docker build, publish,
manifest verification, and container smoke testing all run on GitHub-hosted
Actions runners.

## What the release workflow does

The `Release` workflow:

- reruns the .NET server build and tests on Linux
- reruns web build and unit tests on Linux
- reruns the E2E auth smoke on Linux
- builds the Velopack Windows package on `windows-latest`
- publishes `weir-web-dist.zip`
- builds a local, unpushed Docker release candidate
- runs the complete packaged browser/API audit against that candidate, including
  a mounted disposable Refiner file that must pass through byte-identically into
  the processed tree before its watched source is removed, and uploads screenshots
  plus JSON evidence
- builds and pushes Docker tags for linux/amd64 and linux/arm64:
  - `ghcr.io/<owner>/<repo>:X.Y.Z` (the git tag is `vX.Y.Z`; the image tag drops the `v`)
  - `ghcr.io/<owner>/<repo>:latest`
- verifies the published Docker manifest resolves
- runs the published Docker image and waits for `/health`
- creates the GitHub Release

The registry login and Docker push occur only after the unpushed candidate passes
the complete live audit. A failed screen, API check, browser console error, page
error, failed request, bad response, changed pass-through output, or incomplete
source cleanup therefore stops the release before either the versioned image or
`latest` is published. The Windows package smoke runs the same real pass-through
lifecycle against the packaged executable and bundled FFmpeg.

`VITE_SUPPORT_URL` is a Vite build-time variable. Official releases should set the GitHub Actions repository variable `VITE_SUPPORT_URL` to `https://github.com/sponsors/jampat000` so the production frontend and packaged Windows installer include **Settings -> Support**. If that variable is missing, release builds still succeed, but production safely hides the Support tab.

## Registry authentication

The release workflow publishes GHCR images with the repository `GITHUB_TOKEN` and
`packages: write` permission. No personal access token is required for normal releases.

## Release artifacts

| Deliverable | Meaning |
|-------------|---------|
| `Tag + source tree` | Canonical source snapshot for the release. |
| `weir-web-dist.zip` | Static production build of `apps/web/dist`. The Weir server is still required. |
| `Weir-win-Setup.exe` | Windows desktop installer (Velopack) with .NET tray host, bundled .NET server (`server\WeirServer.exe`), bundled web UI, bundled FFmpeg, and delta update support. |
| `ghcr.io/<owner>/<repo>:X.Y.Z` | Versioned all-in-one container image (linux/amd64 and linux/arm64). |
| `ghcr.io/<owner>/<repo>:latest` | Latest stable container image. |

## Windows package

The Velopack-based Windows package is the supported Windows release artifact. Release builds produce a setup exe, full nupkg, and delta nupkg under `dist/windows/releases/`.

If you build the Windows package locally and want the installer to include **Settings -> Support**, set `VITE_SUPPORT_URL` before running `packaging/windows/build-velopack.ps1`:

```powershell
$env:VITE_SUPPORT_URL = "https://github.com/sponsors/jampat000"
powershell -ExecutionPolicy Bypass -File packaging/windows/build-velopack.ps1
```

After installing:

1. Launch `Weir` from the Start Menu or desktop shortcut.
2. Weir starts in the user session, not as a Windows service.
3. The .NET tray app (`Weir.exe`) launches the Weir server (`server\WeirServer.exe`) as a child process, watches it, and restarts it if it stops.
4. The tray icon opens the local app in the browser and exposes `Open Weir`, `Open Data Folder`, `Check for updates`, and `Quit`.
5. Application binaries install under `%LocalAppData%\Weir` (per-user, no admin required).
6. The local runtime root is created under `C:\ProgramData\Weir`.

Updates are handled automatically by the .NET tray app via Velopack. Delta updates keep downloads small and rollback is automatic on failure. No separate updater service is needed.

If an operator runs a manually staged copy without Velopack install metadata, the
tray keeps `Check for updates` visible and opens Settings -> Upgrade for the
browser-based release check. It must not silently remove the update action.

This design is intentional. Running in the user session avoids common NAS or external-drive access issues that affect Windows services, while keeping writable configuration, logs, backups, and the SQLite database out of the application install directory.

## Docker

Stable Docker releases are published from the same tag workflow.

If Docker Desktop is broken or not installed locally, do not block the release
on this workstation. Run the remote validation workflow instead:

```powershell
.\scripts\verify-docker-remote.ps1
```

That command triggers the `Test` workflow for the current ref and watches it.
The Docker image build and Docker smoke test run on GitHub infrastructure.

Pull and run:

```bash
docker pull ghcr.io/jampat000/weir:latest
docker run --rm \
  -p 8788:8788 \
  -v weir-data:/data/weir \
  ghcr.io/jampat000/weir:latest
```

Or use the root `compose.yaml`:

```bash
docker compose pull
docker compose up -d
```

No env file is required for the default all-in-one container path. Create `.env.weir`
only if you want to override defaults such as the image tag or runtime home.

## Not shipped

- Windows service mode
- Windows installer code signing
- NuGet publishing
- npm publishing
- automatic version bumps or release bots

## Related files

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `docs/release-governance.md`
- `docs/smoke-checklists.md`
- `docker/README.md`
- `docs/local-development.md`
