"""Bounded first-run bootstrap: create the initial ``admin`` account only (Phase 6).

Unavailable once **any** user with role ``admin`` exists (active or not — recovery is DB/ops).

**Not** a registration product: no invitations, password reset, or general admin UX here.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mediamop.platform.auth.models import User, UserRole
from mediamop.platform.auth.password import hash_password


def acquire_bootstrap_transaction_lock(db: Session) -> None:
    """Serialize concurrent bootstrap attempts.

    SQLite: ``BEGIN IMMEDIATE`` must be the first statement on the DBAPI connection. Using the
    driver connection avoids SQLAlchemy emitting a deferred ``BEGIN`` before our statement.
    """

    raw = db.connection().connection.driver_connection
    raw.execute("BEGIN IMMEDIATE")


def any_admin_user_exists(db: Session) -> bool:
    cnt = db.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.admin.value),
    )
    return (cnt or 0) > 0


def bootstrap_allowed(db: Session) -> bool:
    return not any_admin_user_exists(db)


def create_initial_admin(db: Session, *, username: str, password: str) -> User:
    """Insert the first admin user. Caller must verify :func:`bootstrap_allowed` first."""

    if any_admin_user_exists(db):
        raise RuntimeError("bootstrap not allowed: an admin user already exists")
    row = User(
        username=username.strip(),
        password_hash=hash_password(password),
        role=UserRole.admin.value,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row
