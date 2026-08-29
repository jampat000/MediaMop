"""An ordered track sorter list on the rule set

Refiner ranked audio tracks with a hardcoded six-key tuple. An operator could pick one of
three policies and three language tiers, but the ranking *inside* a tier was fixed —
"prefer DTS-HD over TrueHD", "prefer 5.1 over 7.1", "prefer the track whose title does not
say Descriptive" all meant a code change.

The columns are seeded empty, and an empty list is read as the default sorter order,
which reproduces the old tuple exactly. So nothing changes on upgrade until somebody
edits the list — and there is a test asserting that against a copy of the original
implementation rather than against a description of it.

Revision ID: 0019_track_sorters
Revises: 0018_file_processing_log
Create Date: 2026-08-29 16:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0019_track_sorters"
down_revision = "0018_file_processing_log"
branch_labels = None
depends_on = None

_RULE_SET_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("audio_sorters_json", sa.Column("audio_sorters_json", sa.Text(), nullable=False, server_default="")),
    ("subtitle_sorters_json", sa.Column("subtitle_sorters_json", sa.Text(), nullable=False, server_default="")),
)


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    present = _columns("refiner_rule_sets")
    for name, column in _RULE_SET_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_rule_sets", column)


def downgrade() -> None:
    present = _columns("refiner_rule_sets")
    for name, _ in _RULE_SET_COLUMNS:
        if name in present:
            op.drop_column("refiner_rule_sets", name)
