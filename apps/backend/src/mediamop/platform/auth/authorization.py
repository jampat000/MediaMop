"""Server-side authorization — deny by default on guarded routes (ADR-0003, Phase 6).

Roles persisted in ``users.role``: ``admin``, ``operator``, ``viewer`` (:class:`UserRole`).

Use ``Depends(require_roles(...))`` or the typed aliases (``RequireAdminDep``, etc.) on routes
that must not rely on authentication alone. Unguarded routes remain public **by omission**;
product/module APIs should import dependencies from here rather than scattering role checks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from mediamop.platform.auth.deps_auth import get_current_user_public
from mediamop.platform.auth.models import UserRole
from mediamop.platform.auth.schemas import UserPublic


def require_roles(*allowed_roles: str) -> Callable[..., UserPublic]:
    """Return a FastAPI dependency that requires ``user.role in allowed_roles``."""

    allowed = frozenset(allowed_roles)

    def _checker(user: UserPublic = Depends(get_current_user_public)) -> UserPublic:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden.",
            )
        return user

    return _checker


RequireAdminDep = Annotated[UserPublic, Depends(require_roles(UserRole.admin.value))]
RequireOperatorDep = Annotated[
    UserPublic,
    Depends(require_roles(UserRole.admin.value, UserRole.operator.value)),
]
AuthenticatedUserDep = Annotated[
    UserPublic,
    Depends(
        require_roles(
            UserRole.admin.value,
            UserRole.operator.value,
            UserRole.viewer.value,
        ),
    ),
]
