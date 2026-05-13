---
sidebar_position: 4
title: Releases
---

# Releases

MediaMop ships three deliverables from each tagged release:

| Deliverable | Description |
|-------------|-------------|
| GitHub Release | Canonical source snapshot for the tag |
| `MediaMopSetup.exe` | Windows desktop installer with tray host and bundled runtime |
| Docker image | `ghcr.io/jampat000/mediamop:vX.Y.Z` and `:latest` |

Additional artifact: `mediamop-web-dist.zip` — static production build of the frontend (backend still required).

## Release process

1. Update version in both files via a normal PR:
   - `apps/backend/pyproject.toml`
   - `apps/web/package.json`
2. Merge to `main` after CI passes
3. Create release notes at `docs/release-notes/vX.Y.Z.md`
4. Create and push an annotated tag:

```bash
git fetch origin
git checkout main
git pull origin main
git tag -a vX.Y.Z -m "MediaMop vX.Y.Z"
git push origin vX.Y.Z
```

Pushing a `v*` tag triggers the release workflow.

## What the release workflow does

- Reruns backend tests, web build, and E2E auth smoke on Linux
- Builds `MediaMopSetup.exe` on Windows
- Publishes `mediamop-web-dist.zip`
- Builds and pushes Docker tags (versioned + `latest`)
- Verifies Docker manifest and runs container health check
- Creates the GitHub Release with release notes

## License

All release artifacts are licensed under AGPL-3.0-or-later.
