"""Per-library settling controls, and the two timestamps that make them observable

An mtime threshold guesses how long writing takes. It is wrong in both directions: too
low and Refiner grabs a file mid-write, too high and everything waits for nothing. A
stalled download that resumes after the threshold has passed still looks ready, because
mtime only says when the last write happened, never whether writing has stopped.

Watching the **size** answers the actual question. These columns are what that needs:

``refiner_libraries``
    ``file_detection_interval_seconds`` — how long the size must hold still.
    ``ignore_size_changes`` — opt out, for a library where the writer is known to be done.
    ``skip_access_tests`` — opt out of the read/write probe.

``refiner_files``
    ``size_changed_at`` — when the size last differed from the previous observation. The
    whole settling decision is ``now - size_changed_at >= interval``.
    ``hold_until`` — when the hold expires, so the Files screen can show a release time
    instead of an indefinite "on hold".

Defaults reproduce today's behaviour: a 30s interval matched to the shipped scan cadence,
neither opt-out set, both timestamps null until a scan observes the file.

Revision ID: 0013_refiner_file_settling
Revises: 0012_refiner_file_states
Create Date: 2026-08-29 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0013_refiner_file_settling"
down_revision = "0012_refiner_file_states"
branch_labels = None
depends_on = None

_LIBRARY_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "file_detection_interval_seconds",
        sa.Column("file_detection_interval_seconds", sa.Integer(), nullable=False, server_default="30"),
    ),
    ("ignore_size_changes", sa.Column("ignore_size_changes", sa.Boolean(), nullable=False, server_default="0")),
    ("skip_access_tests", sa.Column("skip_access_tests", sa.Boolean(), nullable=False, server_default="0")),
)

_FILE_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("size_changed_at", sa.Column("size_changed_at", sa.DateTime(timezone=True), nullable=True)),
    ("hold_until", sa.Column("hold_until", sa.DateTime(timezone=True), nullable=True)),
)


def _existing(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    # 0001 creates every table from the models of its day, so a fresh database can arrive
    # here already carrying these columns. Adding one twice is an error in SQLite.
    present = _existing("refiner_libraries")
    for name, column in _LIBRARY_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_libraries", column)

    present = _existing("refiner_files")
    for name, column in _FILE_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_files", column)


def downgrade() -> None:
    for name, _ in _FILE_COLUMNS:
        op.drop_column("refiner_files", name)
    for name, _ in _LIBRARY_COLUMNS:
        op.drop_column("refiner_libraries", name)
