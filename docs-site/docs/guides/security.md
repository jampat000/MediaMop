---
sidebar_position: 2
title: Security
---

# Security

Weir's security posture and hardening baseline.

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
| `WEIR_SESSION_SECRET` | Signs sessions and CSRF tokens |
| `WEIR_CREDENTIALS_SECRET` | Encrypts saved provider credentials (Sonarr, Radarr, etc.) |
| `WEIR_METRICS_BEARER_TOKEN` | Gates machine access to `/metrics` |

**Keep these separate.** Never commit `.env` files, SQLite databases, or logs.

### Rotating credentials secret

1. Set the new value as `WEIR_CREDENTIALS_SECRET`
2. Add the old value to `WEIR_PREVIOUS_CREDENTIALS_SECRETS`
3. Restart Weir
4. Re-save all provider credentials (Sonarr, Radarr)
5. Remove the old value from `WEIR_PREVIOUS_CREDENTIALS_SECRETS`
6. Restart again

## CI security checks

| Tool | What it checks |
|------|---------------|
| CodeQL | Static analysis of the C# server and the JavaScript/TypeScript web app |
| NuGet vulnerability scan | .NET package vulnerabilities (`node scripts/check-dotnet-vulnerabilities.mjs apps/server/Weir.slnx`; fails on High or Critical) |
| npm audit | JavaScript dependency vulnerabilities |
| Dependabot | Automated dependency update PRs for NuGet, npm, GitHub Actions, and the Python test-runner packages in `tests/requirements.txt` |

The docs build runs an image-format preflight and rejects ICNS, JXL, HEIC, and HEIF before Docusaurus parses repository assets. The current `image-size` advisories are tracked in `dependency-audit-exceptions.json` because the registry does not yet publish a fixed version; the exception has an expiry date and a documented mitigation. When a fixed release is available, update the `image-size` override, remove the exception entries, and keep the preflight as defense in depth.

## Repository controls

- `main` is protected by GitHub branch rules
- Required checks: `weir`, `docker-smoke`, `windows-package-smoke`
- Security vulnerabilities are reported privately through `SECURITY.md`

## Pre-release checklist

1. Confirm no secrets or runtime files are staged
2. Confirm dependency audit jobs pass
3. Confirm CodeQL has no open high-confidence findings
4. Confirm auth smoke tests pass
5. Confirm backup files don't expose secrets
6. Confirm activity/log views don't expose tokens

## Locked out

Weir has one operator account. There is no second admin to let you back in, and no email
reset — the app stores no email address and has no outbound mail path, only webhooks. Recovery is
therefore proof that you can reach the server, which is already the trust boundary: the session
signing key and the database both live under `WEIR_HOME`.

### If you forgot your password

Run the recovery command where Weir is installed. It sets a new password, re-activates the
account, and signs out every existing session. This works only from the server's own console —
it is not reachable over HTTP — because reaching the server's shell is the proof of identity
recovery relies on.

```bash
docker exec weir /opt/weir/Weir recover
```

On a Windows install, run `Weir.exe recover` from the installation directory. Building from
source, use `dotnet run --project apps/server/src/Weir.Host -- recover`.

You will be prompted for the new password (typed without being echoed to the screen), which
keeps it out of your shell history. For scripted use, pass `--password`. To see the accounts
without changing anything, use `--list`.

### If you signed in but are sent straight back to the login page

Your password is not the problem — the browser is discarding the session cookie. This happens
when Weir is reached over plain HTTP while the cookie is forced to HTTPS-only.

The default is `auto`, which marks the cookie HTTPS-only only when a request actually arrives
over HTTPS, so this should not occur unless the setting has been forced. Check for
`WEIR_SESSION_COOKIE_SECURE=true` in your environment and remove it, or set it to `auto`,
then restart.

### Clearing the account

The recovery command above still needs Weir's own process to run, so it is no help when Weir
itself will not start. As a last resort, with Weir stopped, you can clear the accounts directly
and use first-run setup again. Everything else — libraries, connections and settings — lives in
other tables and survives.

The database is at `$WEIR_HOME/data/weir.sqlite3` — `/data/weir/data/weir.sqlite3` inside
Docker, and `C:\ProgramData\Weir\data\weir.sqlite3` on a default Windows install.

1. **Stop Weir.** For Docker, stop the container (`docker compose stop weir`). On Windows,
   choose **Quit** from the tray icon.
2. **Clear the accounts from the host.** The Docker image contains only the Weir server — there
   is no Python or `sqlite3` inside it — so do this on the host, against the data folder you
   mounted at `/data/weir`. (For a named volume, `docker volume inspect weir-data` shows where
   it lives on the host.) Use either:
   - `sqlite3`, if it is installed on the host:

     ```bash
     sqlite3 <data folder>/data/weir.sqlite3 "DELETE FROM user_sessions; DELETE FROM users;"
     ```

   - or, from a clone of the Weir repository with Node.js 24 installed, the reset script with
     `WEIR_HOME` pointed at the data folder:

     ```bash
     WEIR_HOME=<data folder> node scripts/dev-reset-auth.mjs --yes --force
     ```

     On Windows (PowerShell): `$env:WEIR_HOME = "C:\ProgramData\Weir"; node scripts/dev-reset-auth.mjs --yes --force`
3. **Start Weir again** and open `/setup` to create the account again.
