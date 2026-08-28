"""Per-library switch for filesystem events

Refiner walked the whole watched tree on a timer. Watching the filesystem makes a new
file a candidate within seconds instead of within an interval, but it cannot be the only
mechanism: Docker bind mounts, SMB and NFS frequently deliver no events at all.

So the periodic scan stays as the backstop, and this column is the opt-out for shares
where watching is unreliable enough that an operator would rather not be told about it.
It defaults on, because a watcher that fails to start already degrades to polling and
reports itself — the switch is for the case where that report is noise rather than news.

Revision ID: 0014_refiner_watcher
Revises: 0013_refiner_file_settling
Create Date: 2026-08-29 11:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0014_refiner_watcher"
down_revision = "0013_refiner_file_settling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "refiner_libraries" not in set(inspector.get_table_names()):
        return
    # 0001 builds every table from the models of its day, so a fresh database can reach
    # this migration already carrying the column.
    if "file_system_events_enabled" in {c["name"] for c in inspector.get_columns("refiner_libraries")}:
        return
    op.add_column(
        "refiner_libraries",
        sa.Column("file_system_events_enabled", sa.Boolean(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("refiner_libraries", "file_system_events_enabled")
