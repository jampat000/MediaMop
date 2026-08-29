"""An explicit output collision policy, per library

Refiner had exactly one collision behaviour: overwrite. The activity note even called it
the "default Refiner output collision policy", implying there were others. There were not.

A collision is **silent**, which is what makes it worse than it sounds. Two sources
normalising to one output path — a repack alongside the original, or the same title in two
release folders — means the second destroys the first output, and the only trace was a
note in an activity row that may already have aged out under log retention.

``replace`` is the default, so an upgrade changes nothing.

Revision ID: 0022_output_collision_policy
Revises: 0021_sidecar_migration
Create Date: 2026-08-29 19:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0022_output_collision_policy"
down_revision = "0021_sidecar_migration"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


_FILE_COLUMNS: tuple[str, ...] = (
    "output_collision_policy",
    "output_collision_action",
    "output_collision_reason",
)


def upgrade() -> None:
    present = _columns("refiner_libraries")
    if present and "output_collision_policy" not in present:
        op.add_column(
            "refiner_libraries",
            sa.Column("output_collision_policy", sa.Text(), nullable=False, server_default="replace"),
        )

    # The decision lands on the file, not only in an activity note: the note ages out and
    # the question is asked long afterwards.
    present = _columns("refiner_files")
    for name in _FILE_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_files", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    present = _columns("refiner_files")
    for name in _FILE_COLUMNS:
        if name in present:
            op.drop_column("refiner_files", name)
    if "output_collision_policy" in _columns("refiner_libraries"):
        op.drop_column("refiner_libraries", "output_collision_policy")
