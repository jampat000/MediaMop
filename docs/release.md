# MediaMop releases

MediaMop now ships three release deliverables from a tagged release:

1. a GitHub Release for the tagged source snapshot
2. a Windows desktop installer (`MediaMopSetup.exe`)
3. a Docker image published to GitHub Container Registry

The Windows artifact is an installer-based desktop app with a tray host. It is not a Windows service.

## Contract

1. Update the version in both files in a normal PR:
   - `apps/backend/pyproject.toml`
   - `apps/web/package.json`
2. Merge to `main` after `Test / mediamop` passes.
3. Create an annotated tag on the merge commit:

   ```bash
   git fetch origin
   git checkout main
   git pull origin main
   git tag -a vX.Y.Z -m "MediaMop vX.Y.Z"
   git push origin vX.Y.Z
   ```

4. Pushing `v*` triggers `.github/workflows/release.yml`.

## What the release workflow does

The `Release` workflow:

- reruns backend tests on Linux
- reruns web build and unit tests on Linux
- reruns the E2E auth smoke on Linux
- builds `MediaMopSetup.exe` on `windows-latest`
- publishes `mediamop-web-dist.zip`
- builds and pushes Docker tags:
  - `ghcr.io/<owner>/<repo>:vX.Y.Z`
  - `ghcr.io/<owner>/<repo>:latest`
- verifies the published Docker manifest resolves
- runs the published Docker image and waits for `/health`
- creates the GitHub Release

## Registry authentication

The release workflow publishes GHCR images with the repository `GITHUB_TOKEN` and
`packages: write` permission. No personal access token is required for normal releases.

## Release artifacts

| Deliverable | Meaning |
|-------------|---------|
| `Tag + source tree` | Canonical source snapshot for the release. |
| `mediamop-web-dist.zip` | Static production build of `apps/web/dist`. Backend still required. |
| `MediaMopSetup.exe` | Windows desktop installer with tray host, bundled backend runtime, bundled web UI, and Start Menu integration. |
| `ghcr.io/<owner>/<repo>:vX.Y.Z` | Versioned all-in-one container image. |
| `ghcr.io/<owner>/<repo>:latest` | Latest stable container image. |

## Windows installer

`MediaMopSetup.exe` is the supported Windows release artifact.

After installing it:

1. Launch `MediaMop` from the Start Menu or desktop shortcut.
2. MediaMop starts in the user session, not as a Windows service.
3. The tray icon opens the local app in the browser and exposes `Open MediaMop`, `Open Data Folder`, and `Quit`.
4. The local runtime root is created under `%LOCALAPPDATA%\MediaMop`.

This design is intentional. Running in the user session avoids common NAS or external-drive access issues that affect Windows services.

## Docker

Stable Docker releases are published from the same tag workflow.

Pull and run:

```bash
docker pull ghcr.io/jampat000/mediamop:latest
docker run --rm \
  -p 8788:8788 \
  -v mediamop-data:/data/mediamop \
  ghcr.io/jampat000/mediamop:latest
```

Or use the root `compose.yaml`:

```bash
docker compose pull
docker compose up -d
```

No env file is required for the default all-in-one container path. Create `.env.mediamop`
only if you want to override defaults such as the image tag or runtime home.

## Not shipped

- Windows service mode
- Windows installer code signing
- PyPI publishing
- npm publishing
- automatic version bumps or release bots

## Related files

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `docker/README.md`
- `docs/local-development.md`
