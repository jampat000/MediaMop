"""Double-submit CSRF tokens for cookie session auth (ADR-0003).

Tokens are **signed** (``itsdangerous.TimestampSigner``) with ``MEDIAMOP_SESSION_SECRET``.
They are **not** JWTs and are **not** stored in localStorage.

Scope in Phase 5: login, logout, and issuing endpoint ``GET /auth/csrf``. Unsafe browser POSTs
should also pass :func:`validate_browser_post_origin` when trusted browser origins are configured
(``MEDIAMOP_TRUSTED_BROWSER_ORIGINS`` if set, otherwise ``MEDIAMOP_CORS_ORIGINS``). In
``MEDIAMOP_ENV=development``, each configured ``http(s)://localhost`` / ``127.0.0.1`` origin is
implicitly paired with the other hostname at the same port so login works regardless of which URL
you open.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from mediamop.core.config import MediaMopSettings

CSRF_SIGNER_SALT = "mediamop-csrf-v1"
CSRF_MAX_AGE_SEC = 3600
CSRF_SUBJECT = "csrf"


def _signer(secret: str) -> TimestampSigner:
    return TimestampSigner(secret, salt=CSRF_SIGNER_SALT)


def issue_csrf_token(secret: str) -> str:
    if not secret.strip():
        raise ValueError("session secret required for CSRF")
    return _signer(secret).sign(CSRF_SUBJECT.encode("utf-8")).decode("utf-8")


def verify_csrf_token(secret: str, token: str, *, max_age_sec: int = CSRF_MAX_AGE_SEC) -> bool:
    if not (token or "").strip() or not (secret or "").strip():
        return False
    try:
        raw = _signer(secret).unsign(token.encode("utf-8"), max_age=max_age_sec)
        return raw.decode("utf-8") == CSRF_SUBJECT
    except (BadSignature, SignatureExpired, UnicodeDecodeError):
        return False


def validate_browser_post_origin(request: Request, settings: MediaMopSettings) -> None:
    """Defense in depth: when trusted origins are configured, require Origin or Referer match."""

    trusted = settings.trusted_browser_origins
    if not trusted:
        return

    normalized = {o.rstrip("/") for o in trusted}
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        if origin.rstrip("/") not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origin not allowed.",
            )
        return

    referer = (request.headers.get("referer") or "").strip()
    if referer:
        parsed = urlparse(referer)
        base = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if base not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Referer not allowed.",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Missing Origin or Referer for browser POST.",
    )


def require_session_secret(settings: MediaMopSettings) -> str:
    s = (settings.session_secret or "").strip()
    if not s:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MEDIAMOP_SESSION_SECRET must be set for auth endpoints.",
        )
    return s
