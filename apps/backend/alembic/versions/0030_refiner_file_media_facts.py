"""What each file actually is, kept on the file row.

Refiner probes every file it takes custody of, but most of the result only ever reached the
per-pass log blob. Resolution was already kept on the row for runner weighting; codec, track
counts and duration were not, so the UI could say a file was queued without being able to say
what it *is* — which is exactly the detail an operator needs to judge it.

These are denormalised from the probe deliberately. They are written once per pass, not
continuously, so they cost one extra UPDATE on work that already writes to this row.

Revision ID: 0030_refiner_file_media_facts
Revises: 0029_case_insensitive_usernames
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0030_refiner_file_media_facts"
down_revision = "0029_case_insensitive_usernames"
branch_labels = None
depends_on = None

# ``video_width`` and ``video_height`` already exist and are already written at probe time for
# runner weighting (#338), so resolution is not added here — only the facts that had nowhere to go.
# Nullable throughout: a file that has not been probed yet has no answer, and "unknown" must be
# distinguishable from "no audio tracks". Built per call rather than shared, because a Column
# object cannot be attached to a table twice.
_COLUMNS: tuple[tuple[str, type[sa.types.TypeEngine]], ...] = (
    ("video_codec", sa.Text),
    ("audio_track_count", sa.Integer),
    ("subtitle_track_count", sa.Integer),
    ("duration_seconds", sa.Float),
)


def _existing() -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns("refiner_files")}


def upgrade() -> None:
    present = _existing()
    for name, column_type in _COLUMNS:
        if name not in present:
            op.add_column("refiner_files", sa.Column(name, column_type(), nullable=True))


def downgrade() -> None:
    present = _existing()
    for name, _ in _COLUMNS:
        if name in present:
            op.drop_column("refiner_files", name)
