# Release Governance

This is the canonical governance checklist for keeping MediaMop releases controlled and repeatable.

## GitHub repository controls

- `main` is protected by the active `Owner-Only Main Protection` ruleset.
- Direct deletion and force-pushes to `main` are blocked.
- Pull requests into `main` require conversation resolution.
- Code-owner review is required by the ruleset. `.github/CODEOWNERS` owns the full tree.
- Required status checks for `main` are:
  - `mediamop`
  - `docker-smoke`
  - `windows-package-smoke`
- The repo Wiki is disabled. Public docs live in the repository.
- Issues are enabled and use structured templates.
- Releases are tag-driven from `v*` tags.

## Before every release

1. Confirm the working tree is clean.
2. Confirm `main` is up to date with `origin/main`.
3. Confirm `.github/workflows/ci.yml` and `.github/workflows/release.yml` still expose the required check names listed above.
4. Confirm Dependabot has no stale action-runtime holds that conflict with the workflow pins.
5. Confirm open issues tagged `priority: critical` or `priority: high` are either fixed, intentionally deferred, or not release-blocking.
6. Run the release path from `docs/release.md`.

## After every release

1. Confirm the GitHub Release exists for the pushed tag.
2. Confirm `MediaMopSetup.exe` is attached to the release.
3. Confirm the GHCR image exists for both `vX.Y.Z` and `latest`.
4. Confirm the release workflow completed `mediamop`, Docker publish, Docker smoke, and Windows package jobs.
5. Open a follow-up issue for any manual smoke-test failure.
