"""Clear local auth tables so first-run bootstrap (/setup) works again.

Use when you forgot the admin password or your DB was seeded by integration tests
(username ``alice``, password ``test-password-strong``).

Uses the SQLite file from ``MEDIAMOP_HOME`` / ``MEDIAMOP_DB_PATH`` (e.g. from ``apps/backend/.env``).
Refuses to run unless ``MEDIAMOP_ENV`` is ``development`` unless you pass ``--force``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = _REPO_ROOT / "apps" / "backend"
_BACKEND_SRC = _BACKEND_ROOT / "src"


def _bootstrap_path() -> None:
    if str(_BACKEND_SRC) not in sys.path:
        sys.path.insert(0, str(_BACKEND_SRC))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print usernames/roles and exit (no changes).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to delete users and sessions.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow running when MEDIAMOP_ENV is not development.",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        print(f"FAIL: {exc}. Install backend deps: pip install -e ./apps/backend", file=sys.stderr)
        return 2

    load_dotenv(_BACKEND_ROOT / ".env")

    _bootstrap_path()

    try:
        from sqlalchemy import delete, select
        from sqlalchemy.orm import Session

        from mediamop.core.config import MediaMopSettings
        from mediamop.core.db import create_db_engine, create_session_factory
        from mediamop.platform.auth.models import User, UserSession
    except ImportError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    settings = MediaMopSettings.load()

    env = (settings.env or "").strip().lower()
    if env != "development" and not args.force:
        print(
            f"FAIL: MEDIAMOP_ENV is {settings.env!r}, not development. "
            "Use --force if you really mean to wipe auth on this database.",
            file=sys.stderr,
        )
        return 2

    eng = create_db_engine(settings)
    fac = create_session_factory(eng)

    with fac() as db:
        assert isinstance(db, Session)
        if args.list:
            users = list(db.scalars(select(User).order_by(User.username)).all())
            if not users:
                print("No users in database — open /setup to create the first admin.")
                return 0
            print("Users in database:")
            for row in users:
                print(f"  - {row.username!r}  role={row.role!r}  active={row.is_active}")
            print(
                "\nTip: integration tests often seed admin "
                "`alice` / `test-password-strong`.\n"
                "To start over, run:  py -3 scripts/dev_reset_auth.py --yes",
            )
            return 0

        if not args.yes:
            print(
                "This will DELETE all rows in user_sessions and users "
                "(you can use /setup again afterward).\n"
                "Re-run with --yes to confirm, or --list to see accounts.",
                file=sys.stderr,
            )
            return 1

        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.commit()

    print("OK: Cleared sessions and users.")
    print("Open http://127.0.0.1:8782/setup (or your web URL) to create the admin account again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
