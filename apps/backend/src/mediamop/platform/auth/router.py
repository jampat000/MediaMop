"""Cookie session auth JSON API under ``/api/v1/auth/*``."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Header, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.platform.auth import schemas
from mediamop.platform.auth import service as auth_service
from mediamop.platform.auth.abuse import (
    raise_if_bootstrap_rate_limited,
    raise_if_login_rate_limited,
)
from mediamop.platform.auth.authorization import RequireAdminDep
from mediamop.platform.auth import bootstrap as bootstrap_service
from mediamop.platform.auth.bootstrap_status_db import raise_http_for_bootstrap_status_db
from mediamop.platform.auth.csrf import (
    issue_csrf_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity import service as activity_service
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _csrf_from_header_or_body(
    header_token: str | None,
    body_token: str | None,
) -> str:
    t = (header_token or body_token or "").strip()
    if not t:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing CSRF token (X-CSRF-Token header or body csrf_token).",
        )
    return t


@router.get("/csrf", response_model=schemas.CsrfOut)
def get_csrf(settings: SettingsDep) -> schemas.CsrfOut:
    secret = require_session_secret(settings)
    return schemas.CsrfOut(csrf_token=issue_csrf_token(secret))


@router.post("/login", response_model=schemas.LoginOut)
def post_login(
    request: Request,
    body: schemas.LoginIn,
    db: DbSessionDep,
    settings: SettingsDep,
    response: Response,
) -> schemas.LoginOut:
    raise_if_login_rate_limited(request)
    secret = require_session_secret(settings)
    validate_browser_post_origin(request, settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    uname = body.username.strip()
    result = auth_service.login_user(
        db,
        username=uname,
        password=body.password,
        settings=settings,
    )
    if result is None:
        logger.warning("auth event: login failed (username=%s)", uname)
        activity_service.maybe_record_login_failed(db, username=uname)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    user, raw = result
    logger.info("auth event: login succeeded (user_id=%s username=%s)", user.id, user.username)
    activity_service.record_activity_event(
        db,
        event_type=activity_constants.AUTH_LOGIN_SUCCEEDED,
        module="auth",
        title="Signed in",
        detail=user.username,
    )

    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw,
        max_age=settings.session_absolute_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )
    response.headers.setdefault("Cache-Control", "no-store, private")
    return schemas.LoginOut(user=schemas.UserPublic(**auth_service.user_public(user)))


@router.get("/bootstrap/status", response_model=schemas.BootstrapStatusOut)
def get_bootstrap_status(db: DbSessionDep) -> schemas.BootstrapStatusOut:
    """Report whether the initial ``admin`` account may still be created (Phase 6)."""

    try:
        allowed = bootstrap_service.bootstrap_allowed(db)
    except (OperationalError, ProgrammingError) as exc:
        raise_http_for_bootstrap_status_db(exc)
    if allowed:
        return schemas.BootstrapStatusOut(
            bootstrap_allowed=True,
            reason="no_admin_user",
        )
    return schemas.BootstrapStatusOut(
        bootstrap_allowed=False,
        reason="admin_already_exists",
    )


@router.post("/bootstrap", response_model=schemas.BootstrapOut)
def post_bootstrap(
    request: Request,
    body: schemas.BootstrapIn,
    db: DbSessionDep,
    settings: SettingsDep,
) -> schemas.BootstrapOut:
    """Create the first ``admin`` user once per deployment (guarded + rate limited).

    Requires the same CSRF + Origin/Referer posture as ``POST /login``. After success,
    callers use ``POST /login`` normally. Not available once any ``admin`` user exists.
    """

    raise_if_bootstrap_rate_limited(request)
    secret = require_session_secret(settings)
    validate_browser_post_origin(request, settings)
    if not verify_csrf_token(secret, body.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )
    logger.info("auth event: bootstrap attempted")
    bootstrap_service.acquire_bootstrap_transaction_lock(db)
    if not bootstrap_service.bootstrap_allowed(db):
        logger.warning("auth event: bootstrap denied (admin already exists)")
        activity_service.maybe_record_bootstrap_denied(db)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap is not available: an admin user already exists.",
        )
    try:
        user = bootstrap_service.create_initial_admin(
            db,
            username=body.username.strip(),
            password=body.password,
        )
    except IntegrityError as exc:
        logger.warning("auth event: bootstrap failed (username conflict)")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
        ) from exc
    logger.info(
        "auth event: bootstrap succeeded (user_id=%s username=%s)",
        user.id,
        user.username,
    )
    activity_service.record_activity_event(
        db,
        event_type=activity_constants.AUTH_BOOTSTRAP_SUCCEEDED,
        module="auth",
        title="Initial admin created",
        detail=user.username,
    )
    return schemas.BootstrapOut(
        message="Bootstrap complete. Sign in with POST /api/v1/auth/login.",
        username=user.username,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def post_logout(
    request: Request,
    db: DbSessionDep,
    settings: SettingsDep,
    response: Response,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    body: schemas.LogoutIn | None = Body(default=None),
) -> Response:
    secret = require_session_secret(settings)
    validate_browser_post_origin(request, settings)
    token = _csrf_from_header_or_body(x_csrf_token, body.csrf_token if body else None)
    if not verify_csrf_token(secret, token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired CSRF token.",
        )

    raw = (request.cookies.get(settings.session_cookie_name) or "").strip() or None
    if raw:
        pair = auth_service.load_valid_session_for_request(db, raw, settings)
        if pair:
            _srow, user = pair
            activity_service.record_activity_event(
                db,
                event_type=activity_constants.AUTH_LOGOUT,
                module="auth",
                title="Signed out",
                detail=user.username,
            )
        revoked = auth_service.logout_by_cookie(db, raw, settings)
        if revoked:
            logger.info("auth event: logout (session revoked)")
        else:
            logger.info("auth event: logout (no active session matched cookie)")
    else:
        logger.info("auth event: logout (no session cookie)")
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
    )
    response.headers.setdefault("Cache-Control", "no-store, private")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=schemas.MeOut)
def get_me(current: UserPublicDep) -> schemas.MeOut:
    return schemas.MeOut(user=current)


@router.get("/admin/ping")
def admin_ping(_admin: RequireAdminDep) -> dict[str, bool]:
    """Minimal authenticated probe for the admin-only dependency (Phase 6 tests + ops)."""

    return {"ok": True}
