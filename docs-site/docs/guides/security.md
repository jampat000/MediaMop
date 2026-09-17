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
4. Re-save all provider credentials (Sonarr, Radarr)
5. Remove the old value from `MEDIAMOP_PREVIOUS_CREDENTIALS_SECRETS`
6. Restart again

## CI security checks

| Tool | What it checks |
|------|---------------|
| CodeQL | Static analysis for security vulnerabilities |
| Bandit | Python security linting |
| pip-audit | Python dependency vulnerabilities |
| npm audit | JavaScript dependency vulnerabilities |

The docs build runs an image-format preflight and rejects ICNS, JXL, HEIC, and HEIF before Docusaurus parses repository assets. The current `image-size` advisories are tracked in `dependency-audit-exceptions.json` because the registry does not yet publish a fixed version; the exception has an expiry date and a documented mitigation. When a fixed release is available, update the `image-size` override, remove the exception entries, and keep the preflight as defense in depth.
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

## Locked out

MediaMop has one operator account. There is no second admin to let you back in, and no email
reset — the app stores no email address and has no outbound mail path, only webhooks. Recovery is
therefore proof that you can reach the server, which is already the trust boundary: the session
signing key and the database both live under `MEDIAMOP_HOME`.

### If you forgot your password

Run the recovery command where MediaMop is installed. It sets a new password, re-activates the
account, and signs out every existing session.

```bash
docker compose exec mediamop mediamop-recover
```

On a Windows install, run `mediamop-recover` from the installation directory.

You will be prompted for the new password, which keeps it out of your shell history. For
scripted use, pass `--password`. To see the accounts without changing anything, use `--list`.

### If you signed in but are sent straight back to the login page

Your password is not the problem — the browser is discarding the session cookie. This happens
when MediaMop is reached over plain HTTP while the cookie is forced to HTTPS-only.

The default is `auto`, which marks the cookie HTTPS-only only when a request actually arrives
over HTTPS, so this should not occur unless the setting has been forced. Check for
`MEDIAMOP_SESSION_COOKIE_SECURE=true` in your environment and remove it, or set it to `auto`,
then restart.

### If the server will not start at all

As a last resort you can clear the accounts directly and use first-run setup again. Everything
else — libraries, connections and settings — lives in other tables and survives.

```bash
docker compose exec mediamop /opt/mediamop/.venv/bin/python -c "import sqlite3; c=sqlite3.connect('/data/mediamop/data/mediamop.sqlite3'); c.execute('DELETE FROM user_sessions'); c.execute('DELETE FROM users'); c.commit(); print('cleared')"
```

The database is at `$MEDIAMOP_HOME/data/mediamop.sqlite3` — `/data/mediamop/data/mediamop.sqlite3`
in Docker, and `C:\ProgramData\MediaMop\data\mediamop.sqlite3` on a default Windows install. Stop
the server first. Then open `/setup` to create the account again.
