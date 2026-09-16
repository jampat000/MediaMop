"""Usernames match without regard to case.

SQLite compares TEXT case-sensitively, so an account created as ``Admin`` could not sign in as
``admin`` — and the resulting "Invalid username or password" sent operators hunting for a
password problem that did not exist. Sonarr, Radarr, Jellyfin and Plex all fold case here.

A unique index on ``lower(username)`` makes the database enforce what the lookup now assumes.

Revision ID: 0029_case_insensitive_usernames
Revises: 0028_refiner_detection_windows
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0029_case_insensitive_usernames"
down_revision = "0028_refiner_detection_windows"
branch_labels = None
depends_on = None

_INDEX = "ux_users_username_lower"

# Reflection cannot see this index: SQLAlchemy skips expression-based indexes with a warning,
# so `inspect(...).get_indexes("users")` reports nothing and a re-run would try to create it a
# second time. SQLite's own IF NOT EXISTS is the reliable guard here, and this product is
# SQLite-only by construction.


def upgrade() -> None:
    bind = op.get_bind()

    # Refuse rather than destroy. An install that somehow holds both `Admin` and `admin` has two
    # real accounts, and silently dropping either one loses a password nobody can recover. The
    # operator is told exactly which names collide so they can rename one and retry.
    duplicates = bind.execute(
        sa.text(
            "SELECT lower(username) AS folded, count(*) AS n, group_concat(username, ', ') AS names "
            "FROM users GROUP BY lower(username) HAVING n > 1",
        ),
    ).fetchall()
    if duplicates:
        detail = "; ".join(f"{row.folded!r} is held by {row.names}" for row in duplicates)
        msg = (
            "Cannot make usernames case-insensitive while accounts differ only by capitalisation: "
            f"{detail}. Rename or remove one of each pair, then run the migration again."
        )
        raise RuntimeError(msg)

    bind.execute(
        sa.text(f"CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX} ON users (lower(username))"),
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text(f"DROP INDEX IF EXISTS {_INDEX}"))
