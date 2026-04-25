# Security Hardening

This checklist defines the current practical hardening baseline for MediaMop.

## Authentication and setup

- First-run bootstrap is only available when no admin user exists.
- Passwords shorter than 8 characters must be blocked by both frontend and backend validation.
- Login and bootstrap routes are rate-limited.
- Authenticated state-changing browser requests require CSRF protection.
- Session cookies are HTTP-only.
- Secure cookies should be enabled when deployed behind HTTPS.
- Existing users must persist across restarts and upgrades.

## Secrets and private data

- Real `.env` files must never be committed.
- Runtime SQLite databases must never be committed.
- Logs, backups, media paths, API keys, provider tokens, and session secrets must never be committed.
- Public issue logs must redact secrets, private hostnames, and private filesystem paths.
- Docker can generate a persistent session secret when one is not provided.

## Repository and dependency controls

- `main` is protected by GitHub rules.
- Required checks are `mediamop`, `docker-smoke`, and `windows-package-smoke`.
- Dependabot is enabled for Python and GitHub Actions dependencies.
- CodeQL code scanning runs on `main`, pull requests to `main`, weekly schedule, and manual dispatch.
- Security vulnerabilities are reported privately through `SECURITY.md`.
- Public issues are not used for unpatched vulnerabilities.

## Release controls

- Releases are built from tagged source.
- Windows and Docker artifacts are produced by GitHub Actions.
- Local Docker Desktop is not required to validate Docker packaging.
- Release artifacts remain under AGPL-3.0-or-later.

## Ongoing checks

Run this list before any major release:

1. Confirm no secrets or runtime files are staged.
2. Confirm dependency audit jobs pass.
3. Confirm CodeQL has no open high-confidence security findings.
4. Confirm auth setup, login, logout, and password validation smoke tests pass.
5. Confirm backup files do not expose secrets in public docs, logs, or screenshots.
6. Confirm activity/log views do not expose tokens or internal implementation details to normal users.
