"""Recovery from the server console (#454).

The product has one operator account, no second admin and no email reset, so this command is the
only supported way back in after a forgotten password.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from weir.core.config import WeirSettings
from weir.core.db import create_db_engine, create_session_factory
from weir.platform.activity import constants as activity_constants
from weir.platform.activity.models import ActivityEvent
from weir.platform.auth.models import User, UserRole, UserSession
from weir.platform.auth.password import hash_password, verify_password
from weir.platform.auth.recover import main, reset_account_password
from weir.platform.auth.sessions import (
    compute_absolute_expiry,
    generate_raw_session_token,
    hash_session_token,
)

_OLD = "old-password-strong"
_NEW = "brand-new-password-strong"


@pytest.fixture
def db_session() -> Iterator[Session]:
    settings = WeirSettings.load()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with factory() as session:
        session.execute(delete(UserSession))
        session.execute(delete(User))
        session.commit()
        yield session
        session.rollback()
        session.execute(delete(UserSession))
        session.execute(delete(User))
        session.commit()


def _seed(db: Session, *, active: bool = True, sessions: int = 0) -> User:
    user = User(
        username="james",
        password_hash=hash_password(_OLD),
        role=UserRole.admin.value,
        is_active=active,
    )
    db.add(user)
    db.flush()
    for _ in range(sessions):
        db.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_session_token(generate_raw_session_token()),
                absolute_expires_at=compute_absolute_expiry(),
            ),
        )
    db.flush()
    return user


def test_password_is_replaced(db_session: Session) -> None:
    user = _seed(db_session)
    reset_account_password(db_session, user, _NEW)

    assert verify_password(_NEW, user.password_hash) is True
    assert verify_password(_OLD, user.password_hash) is False


def test_every_session_is_revoked(db_session: Session) -> None:
    """Whoever locked the operator out must not stay signed in."""

    user = _seed(db_session, sessions=3)
    revoked = reset_account_password(db_session, user, _NEW)

    assert revoked == 3
    rows = list(db_session.scalars(select(UserSession).where(UserSession.user_id == user.id)))
    assert rows and all(row.revoked_at is not None for row in rows)


def test_an_inactive_account_is_reactivated(db_session: Session) -> None:
    """A deactivated sole admin is its own lockout, so recovery must clear it (#456)."""

    user = _seed(db_session, active=False)
    reset_account_password(db_session, user, _NEW)
    assert user.is_active is True


def test_a_weak_password_is_refused(db_session: Session) -> None:
    user = _seed(db_session)
    with pytest.raises(ValueError):
        reset_account_password(db_session, user, "password")

    assert verify_password(_OLD, user.password_hash) is True


def test_recovery_is_recorded_in_activity(db_session: Session) -> None:
    user = _seed(db_session)
    reset_account_password(db_session, user, _NEW)
    db_session.flush()

    events = list(
        db_session.scalars(
            select(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.AUTH_PASSWORD_CHANGED,
            ),
        ),
    )
    assert events, "a recovery must be visible in history"
    assert "james" in (events[-1].detail or "")


def test_cli_resets_and_reports(db_session: Session, capsys: pytest.CaptureFixture[str]) -> None:
    user = _seed(db_session, sessions=2)
    db_session.commit()

    assert main(["--username", "james", "--password", _NEW]) == 0

    out = capsys.readouterr().out
    assert "james" in out
    assert "2 signed-in session(s) were ended" in out

    db_session.expire_all()
    refreshed = db_session.get(User, user.id)
    assert refreshed is not None
    assert verify_password(_NEW, refreshed.password_hash) is True


def test_cli_refuses_an_unknown_account(
    db_session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed(db_session)
    db_session.commit()

    assert main(["--username", "nobody", "--password", _NEW]) != 0
    assert "nobody" in capsys.readouterr().err


def test_cli_says_so_when_there_is_nothing_to_recover(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fresh install should be pointed at /setup, not given a confusing failure."""

    assert main(["--username", "nobody", "--password", _NEW]) != 0
    assert "/setup" in capsys.readouterr().err


def test_cli_list_does_not_change_anything(
    db_session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user = _seed(db_session)
    db_session.commit()

    assert main(["--list"]) == 0
    assert "james" in capsys.readouterr().out

    db_session.expire_all()
    refreshed = db_session.get(User, user.id)
    assert refreshed is not None
    assert verify_password(_OLD, refreshed.password_hash) is True
