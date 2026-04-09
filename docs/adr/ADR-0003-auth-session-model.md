# ADR-0003: Auth and session model (MediaMop)

## Status

Accepted — direction locked; **implementation deferred** beyond Phase 1 spine (2026-04-05).

## Context

The product requires **secure-by-default** web authentication: **server-side sessions** with **hardened cookies**, **CSRF** protection for unsafe browser-initiated requests, **Argon2id** password hashing, and **no browser-stored JWT as the default** for the primary UI. Optional **OIDC** may be added later without rewriting core authorization boundaries. The **Fetcher** application (separate repository) uses a different auth approach; MediaMop **does not** inherit that implementation wholesale.

## Decision

1. **Primary web authentication** for MediaMop will use **server-side sessions** (session identifiers or records tracked server-side) with cookies that are **HttpOnly**, **Secure** when served over HTTPS, **SameSite=Lax** by default, and tied to **logout invalidation**, **idle timeout**, and **absolute timeout** once implemented.

2. **Passwords** use **Argon2id** (not legacy pbkdf2/bcrypt defaults from spikes).

3. **CSRF** is required for **state-changing** browser requests (forms and cookie-authenticated POST/PUT/PATCH/DELETE) using a pattern consistent with the framework (double-submit token or equivalent).

4. **Authorization** is enforced **server-side** on every protected action; default **deny**.

5. **Roles** will evolve toward a small set (**owner/admin**, **operator**, **viewer**); Phase 1 does **not** implement roles—only documents the direction.

6. **Bootstrap/setup** flows are **sensitive**; **Phase 6** adds in-process rate limits on login/bootstrap and a bounded first-**admin** bootstrap API; distributed limits and audit logging remain deferred.

7. **API clients** may eventually use **Bearer tokens** or similar for machine access; such tokens are **not** the default path for the **interactive React shell** stored in `localStorage`.

## Consequences

- Any historical Jinja/SQLite spike (outside this repository) is **not** the reference implementation for the final MediaMop auth stack.
- New auth code must live under **`apps/backend/src/mediamop/platform/`** (or a dedicated submodule) when implemented, and must satisfy this ADR.

## Compliance — Phase 1

- **No** full auth stack is required in Phase 1; **health** and scaffolding only.
- Any temporary dev endpoints must not be mistaken for production auth—keep them out of the spine until platform auth is implemented to ADR-0003.

## Compliance — Phase 3

- **`platform/auth/`** exists as **files and documentation only** — **no** mounted login routes, **no** JWT-for-browser default, **no** localStorage session story.
- Comments in `sessions.py` / `csrf.py` describe the **server-side session** target; legacy spikes are **not** the reference implementation.

## Compliance — Phase 4 (real foundation, not finished product auth)

- **Passwords**: `platform/auth/password.py` implements **Argon2id** (via `argon2-cffi`) for `users.password_hash`.
- **Persistence**: `User` and `UserSession` ORM models match the **server-side session** direction (opaque future cookie → row by id; **only** a SHA-256 **hash** of a high-entropy token stored server-side).
- **Helpers**: `sessions.py` encodes **absolute expiry**, **idle window**, **revocation**, and **validity** checks.
- **Phase 5 update**: JSON **login/logout/me/csrf** routes and cookie issuance are implemented under ``/api/v1/auth`` (see **Phase 5** below). Still **not** a full account/onboarding product: no self-service registration, reset, or admin role APIs in the spine yet; module routes do not enforce **authorization** dependencies beyond authentication.

## Compliance — Phase 5 (auth boundary, JSON API)

**Implemented (spine only — not full product onboarding)**

- **Routes** under ``/api/v1/auth/``: ``GET /csrf``, ``POST /login``, ``POST /logout``, ``GET /me`` — cookie session, **no** browser JWT, **no** localStorage.
- **CSRF**: Signed tokens via ``itsdangerous`` + ``MEDIAMOP_SESSION_SECRET``; **unsafe browser POSTs** validate **Origin/Referer** when trusted origins are configured (Phase 6: ``MEDIAMOP_TRUSTED_BROWSER_ORIGINS`` or ``MEDIAMOP_CORS_ORIGINS``).
- **Cookie**: Opaque token in ``MEDIAMOP_SESSION_COOKIE_NAME`` (default ``mediamop_session``), **HttpOnly**, **Secure** when configured / production default, **SameSite** from env.
- **Rotation**: ``POST /login`` revokes prior active ``UserSession`` rows for that user before issuing a new session.
- **Deferred (Phase 5 snapshot)**: Registration, password reset, role management APIs, fine-grained **authorization** on module routers, CSRF on non-auth POSTs beyond this foundation. (Bounded bootstrap and authz helpers land in **Phase 6** below.)

## Compliance — Phase 6 (public edge hardening + bounded bootstrap)

**Abuse controls (in-process)**

- Sliding-window rate limits (per process / per peer IP via ``request.client.host``) for ``POST /api/v1/auth/login`` and ``POST /api/v1/auth/bootstrap``. Tunable via ``MEDIAMOP_AUTH_LOGIN_RATE_*`` and ``MEDIAMOP_BOOTSTRAP_RATE_*``. Limits are **not** shared across workers or survives restart — see ``platform/auth/rate_limit.py`` module docstring for tradeoffs. No Redis.

**Security headers**

- ``X-Content-Type-Options: nosniff``, ``Referrer-Policy: strict-origin-when-cross-origin``, API-oriented ``Content-Security-Policy`` (``default-src 'none'``, ``frame-ancestors 'none'``, etc.), ``X-Frame-Options: DENY``. Responses under ``/api/v1/auth`` also get ``Cache-Control: no-store, private``.
- **HSTS** is **off** unless ``MEDIAMOP_SECURITY_ENABLE_HSTS`` is set; only enable when the app is **always** served over HTTPS.

**Trusted browser origins (CSRF defense in depth)**

- ``validate_browser_post_origin`` uses ``MEDIAMOP_TRUSTED_BROWSER_ORIGINS`` when set (comma-separated); otherwise it falls back to ``MEDIAMOP_CORS_ORIGINS``. CORS remains separate middleware; this split allows stricter POST origin policy than ``Access-Control-Allow-Origin`` if needed later.

**Bounded bootstrap**

- ``GET /api/v1/auth/bootstrap/status`` — whether the first ``admin`` user may be created (no CSRF).
- ``POST /api/v1/auth/bootstrap`` — same CSRF + Origin/Referer posture as login; creates **one** initial ``admin`` only while **no** user with role ``admin`` exists. Uses a PostgreSQL **advisory transaction lock** to serialize concurrent bootstrap attempts. After any ``admin`` row exists (active or not), bootstrap returns **403** — recovery is operations/DB, not this API.
- **Not** implemented: invitations, password reset, self-service registration, or general admin user management.

**Authorization baseline**

- ``platform/auth/authorization.py`` exposes ``require_roles(...)``, ``RequireAdminDep``, ``RequireOperatorDep``, ``AuthenticatedUserDep``. Deny-by-default applies to routes that opt into these dependencies; unauthenticated public routes stay public only by omission.
- ``get_current_user_public`` rejects sessions whose ``users.role`` is not one of ``admin`` / ``operator`` / ``viewer`` (**403**).

**Deferred after Phase 6**

- Distributed rate limiting, trusted reverse-proxy client IP parsing, audit logging for auth events, CSRF on non-auth module POSTs, fine-grained RBAC, invitation/onboarding product flows.
