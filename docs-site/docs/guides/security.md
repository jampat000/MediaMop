---
sidebar_position: 2
title: Security
---

# Security

MediaMop's security posture and hardening baseline.

## Authentication

- First-run bootstrap is only available when no admin user exists
- Passwords must be at least 12 characters (enforced frontend and backend)
- Login and bootstrap routes are rate-limited
- Session cookies are HTTP-only
- CSRF protection on all authenticated state-changing requests
- Secure cookies enabled when deployed behind HTTPS

## Secrets management

| Secret | Purpose |
|--------|---------|
| `MEDIAMOP_SESSION_SECRET` | Signs sessions and CSRF tokens |
| `MEDIAMOP_CREDENTIALS_SECRET` | Encrypts saved provider credentials (Sonarr, Radarr, etc.) |
| `MEDIAMOP_METRICS_BEARER_TOKEN` | Gates machine access to `/metrics` |

**Keep these separate.** Never commit `.env` files, SQLite databases, or logs.

### Rotating credentials secret

1. Set the new value as `MEDIAMOP_CREDENTIALS_SECRET`
2. Add the old value to `MEDIAMOP_PREVIOUS_CREDENTIALS_SECRETS`
3. Restart MediaMop
4. Re-save all provider credentials (Pruner, Subber, Sonarr, Radarr)
5. Remove the old value from `MEDIAMOP_PREVIOUS_CREDENTIALS_SECRETS`
6. Restart again

## CI security checks

| Tool | What it checks |
|------|---------------|
| CodeQL | Static analysis for security vulnerabilities |
| Bandit | Python security linting |
| pip-audit | Python dependency vulnerabilities |
| npm audit | JavaScript dependency vulnerabilities |
| Dependabot | Automated dependency update PRs |

## Repository controls

- `main` is protected by GitHub branch rules
- Required checks: `mediamop`, `docker-smoke`, `windows-package-smoke`
- Security vulnerabilities are reported privately through `SECURITY.md`

## Pre-release checklist

1. Confirm no secrets or runtime files are staged
2. Confirm dependency audit jobs pass
3. Confirm CodeQL has no open high-confidence findings
4. Confirm auth smoke tests pass
5. Confirm backup files don't expose secrets
6. Confirm activity/log views don't expose tokens
