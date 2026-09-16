"""A deactivated sole admin must not brick the install (#456).

Sign-in rejects an inactive user, so if the bootstrap gate also counts deactivated rows there is
no way into the application at all and no in-product way back.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.auth.bootstrap import (
    any_admin_user_exists,
    bootstrap_allowed,
    create_initial_admin,
)
from mediamop.platform.auth.models import User, UserRole


@pytest.fixture
def db_session() -> Iterator[Session]:
    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with factory() as session:
        session.execute(delete(User))
        session.commit()
        yield session
        session.rollback()
        session.execute(delete(User))
        session.commit()


def _admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.admin.value)) or 0


def _seed_admin(db: Session, *, username: str, active: bool) -> User:
    row = User(
        username=username,
        password_hash="argon2-placeholder-not-verified-here",
        role=UserRole.admin.value,
        is_active=active,
    )
    db.add(row)
    db.flush()
    return row


def test_active_admin_still_closes_bootstrap(db_session: Session) -> None:
    _seed_admin(db_session, username="alice", active=True)
    assert any_admin_user_exists(db_session) is True
    assert bootstrap_allowed(db_session) is False


def test_inactive_sole_admin_reopens_bootstrap(db_session: Session) -> None:
    _seed_admin(db_session, username="alice", active=False)
    assert any_admin_user_exists(db_session) is False
    assert bootstrap_allowed(db_session) is True


def test_recovering_from_an_inactive_admin_leaves_exactly_one(db_session: Session) -> None:
    """The install must come back with one usable admin, never two rows."""

    _seed_admin(db_session, username="alice", active=False)

    created = create_initial_admin(
        db_session,
        username="alice-again",
        password="recovered-password-strong",
    )

    assert created.is_active is True
    assert _admin_count(db_session) == 1
    assert bootstrap_allowed(db_session) is False
