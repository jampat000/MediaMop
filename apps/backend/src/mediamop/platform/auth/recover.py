"""Operator account recovery from the server's own shell (#454).

MediaMop has one operator account, no second admin to rescue it and — deliberately — no email
reset: ``users`` has no email column and the app has no outbound mail path, only webhooks. So the
recovery factor is **proof that you can reach the server**, which is already the trust boundary:
``session.secret`` and the database both live under ``MEDIAMOP_HOME``. This is the same shape
Sonarr, Radarr, Jellyfin and Home Assistant use.

Run it where MediaMop is installed::

    docker compose exec mediamop mediamop-recover
    mediamop-recover --username james

It resets the password, re-activates the account (an inactive sole admin is its own lockout —
see ``bootstrap.py``), revokes every session so anyone already signed in is turned out, and
records an activity event so the recovery is visible in history.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity import service as activity_service
from mediamop.platform.auth.models import User, UserRole, UserSession
from mediamop.platform.auth.password import hash_password, validate_password_strength
from mediamop.platform.auth.sessions import utcnow

_EXIT_OK = 0
_EXIT_USAGE = 1
_EXIT_FAILED = 2


def _load_account(db: Session, username: str | None) -> User | None:
    stmt = select(User).order_by(User.id)
    if username:
        stmt = stmt.where(func.lower(User.username) == username.strip().lower())
    return db.scalars(stmt).first()


def _list_accounts(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)).all())


def _read_new_password(supplied: str | None) -> str:
    if supplied is not None:
        return supplied
    if not sys.stdin.isatty():
        msg = "No terminal available to prompt for a password. Pass --password instead."
        raise ValueError(msg)
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat new password: ")
    if first != second:
        raise ValueError("The two passwords did not match.")
    return first


def reset_account_password(db: Session, user: User, new_password: str) -> int:
    """Set the password, re-activate, and revoke every session. Returns sessions revoked."""

    validate_password_strength(new_password, username=user.username)
    user.password_hash = hash_password(new_password)
    # An inactive account cannot sign in, so recovery that left this alone would "succeed" and
    # still leave the operator locked out.
    user.is_active = True

    result = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow()),
    )
    revoked = int(getattr(result, "rowcount", 0) or 0)
    db.flush()

    activity_service.record_activity_event(
        db,
        event_type=activity_constants.AUTH_PASSWORD_CHANGED,
        module="auth",
        title="Password recovered from the server",
        detail=(f"{user.username} — reset from the server console. {revoked} signed-in session(s) were ended."),
    )
    return revoked


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mediamop-recover",
        description="Reset the MediaMop operator password from the server.",
    )
    parser.add_argument("--username", help="Account to reset. Optional while there is only one.")
    parser.add_argument(
        "--password",
        help="New password. Omit to be prompted, which keeps it out of your shell history.",
    )
    parser.add_argument("--list", action="store_true", help="List accounts and exit.")
    args = parser.parse_args(argv)

    settings = MediaMopSettings.load()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)

    with factory() as db:
        accounts = _list_accounts(db)

        if args.list:
            if not accounts:
                print("No accounts. Open /setup to create the first one.")
                return _EXIT_OK
            print(f"Accounts in {settings.db_path}:")
            for row in accounts:
                state = "active" if row.is_active else "INACTIVE"
                print(f"  {row.username}  role={row.role}  {state}")
            return _EXIT_OK

        if not accounts:
            print(
                "No accounts exist yet, so there is nothing to recover.\n"
                "Open /setup in a browser to create the operator account.",
                file=sys.stderr,
            )
            return _EXIT_FAILED

        if args.username is None and len(accounts) > 1:
            names = ", ".join(row.username for row in accounts)
            print(f"Several accounts exist. Pass --username. Found: {names}", file=sys.stderr)
            return _EXIT_USAGE

        user = _load_account(db, args.username)
        if user is None:
            print(f"No account named {args.username!r}. Use --list to see them.", file=sys.stderr)
            return _EXIT_FAILED

        try:
            new_password = _read_new_password(args.password)
            revoked = reset_account_password(db, user, new_password)
        except ValueError as exc:
            # Strength and mismatch failures are the operator's to fix, not a crash.
            print(f"Could not reset the password: {exc}", file=sys.stderr)
            return _EXIT_FAILED

        db.commit()

    print(f"Password reset for {user.username!r}.")
    if user.role == UserRole.admin.value:
        print("The account is active and has the admin role.")
    print(f"{revoked} signed-in session(s) were ended — sign in again with the new password.")
    return _EXIT_OK


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())
