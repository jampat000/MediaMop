# ADR-0003: Auth and session model (MediaMop)

## Status

Accepted.

## Context

The product requires **secure-by-default** web authentication: **server-side sessions** with **hardened cookies**, **CSRF** protection for unsafe browser-initiated requests, **Argon2id** password hashing, and **no browser-stored JWT as the default** for the primary UI. Optional **OIDC** may be added later without rewriting core authorization boundaries. The **Fetcher** application (separate repository) uses a different auth approach; MediaMop **does not** inherit that implementation wholesale.

## Decision

1. **Primary web authentication** for MediaMop will use **server-side sessions** (session identifiers or records tracked server-side) with cookies that are **HttpOnly**, **Secure** when served over HTTPS, **SameSite=Lax** by default, and tied to **logout invalidation**, **idle timeout**, and **absolute timeout** once implemented.

2. **Passwords** use **Argon2id** (not legacy pbkdf2/bcrypt defaults from spikes).

3. **CSRF** is required for **state-changing** browser requests (forms and cookie-authenticated POST/PUT/PATCH/DELETE) using a pattern consistent with the framework (double-submit token or equivalent).

4. **Authorization** is enforced **server-side** on every protected action; default **deny**.

5. Roles are a small fixed set: **admin**, **operator**, **viewer**.

6. **Bootstrap/setup** flows are sensitive and rate-limited.

7. **API clients** may eventually use **Bearer tokens** or similar for machine access; such tokens are **not** the default path for the **interactive React shell** stored in `localStorage`.

## Consequences

- Any historical Jinja/SQLite spike (outside this repository) is **not** the reference implementation for the final MediaMop auth stack.
- New auth code must live under **`apps/backend/src/mediamop/platform/`** (or a dedicated submodule) when implemented, and must satisfy this ADR.

## Current implementation snapshot

- **Routes** under ``/api/v1/auth/``: ``GET /csrf``, ``POST /login``, ``POST /logout``, ``GET /me``, ``GET /bootstrap/status``, ``POST /bootstrap``.
- **Sessions** are server-side in `user_sessions`; browser receives an opaque cookie only.
- **Password hashing** uses **Argon2id**.
- **CSRF** uses signed tokens (`itsdangerous`) and unsafe browser POSTs validate trusted origins.
- **Rate limits** cover login/bootstrap paths (in-process).
- **Security headers** include no-store auth responses; HSTS remains opt-in via configuration.
- **Authorization helpers** enforce role checks server-side.

## Deferred work

- Distributed rate limiting
- Trusted proxy client IP parsing
- Audit logging for auth events
- Additional non-auth module authorization/RBAC depth
- Invitation/reset/onboarding product flows
