"""Dependencies: current user from session cookie (server-side ``UserSession`` row)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.api.deps import get_db_session, get_settings
from mediamop.platform.auth import service as auth_service
from mediamop.platform.auth.models import UserRole
from mediamop.platform.auth.schemas import UserPublic

_VALID_SESSION_ROLES = frozenset(
    {UserRole.admin.value, UserRole.operator.value, UserRole.viewer.value},
)


def get_current_user_public(
    request: Request,
    db: Session = Depends(get_db_session),
    settings: MediaMopSettings = Depends(get_settings),
) -> UserPublic:
    raw = (request.cookies.get(settings.session_cookie_name) or "").strip() or None
    pair = auth_service.load_valid_session_for_request(db, raw, settings)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    _row, user = pair
    if user.role not in _VALID_SESSION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid account role.",
        )
    return UserPublic(**auth_service.user_public(user))


UserPublicDep = Annotated[UserPublic, Depends(get_current_user_public)]
