"""Metadata, cover-art and attachment removal on the rule set

Refiner had no metadata handling at all: it planned video, audio and subtitle streams and
copied everything else through untouched, so embedded cover art, stale titles, attached
fonts and container tags all survived a pass.

The cover-art case is the one with teeth. An embedded poster **is** an mjpeg video stream,
and the plan kept every video stream it found — so the poster came through and was counted
as video, leaving anything that reasons about "the video stream" to cope with two.

Every option defaults **off**. A pass that started stripping titles and tags because an
upgrade landed would be changing files nobody asked it to change.

Revision ID: 0020_metadata_rules
Revises: 0019_track_sorters
Create Date: 2026-08-29 17:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0020_metadata_rules"
down_revision = "0019_track_sorters"
branch_labels = None
depends_on = None

_RULE_SET_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("remove_images", sa.Column("remove_images", sa.Boolean(), nullable=False, server_default="0")),
    ("remove_attachments", sa.Column("remove_attachments", sa.Boolean(), nullable=False, server_default="0")),
    ("remove_title", sa.Column("remove_title", sa.Boolean(), nullable=False, server_default="0")),
    (
        "remove_language_tags",
        sa.Column("remove_language_tags", sa.Boolean(), nullable=False, server_default="0"),
    ),
    (
        "remove_other_metadata",
        sa.Column("remove_other_metadata", sa.Boolean(), nullable=False, server_default="0"),
    ),
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
