"""Facts for the read-only Direct Play badge, and which devices the operator owns (#467).

``refiner_files`` gains ``audio_codecs`` and ``video_bit_depth``, filled by the probe the processing
pass already runs. ``suite_settings`` gains ``direct_play_devices``. Nothing here feeds processing.

Revision ID: 0035_direct_play_facts
Revises: 0034_activity_history_facts
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0035_direct_play_facts"
down_revision = "0034_activity_history_facts"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    files = _columns("refiner_files")
    if "audio_codecs" not in files:
        op.add_column("refiner_files", sa.Column("audio_codecs", sa.Text(), nullable=True))
    if "video_bit_depth" not in files:
        op.add_column("refiner_files", sa.Column("video_bit_depth", sa.Integer(), nullable=True))
    if "direct_play_devices" not in _columns("suite_settings"):
        op.add_column("suite_settings", sa.Column("direct_play_devices", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    if "direct_play_devices" in _columns("suite_settings"):
        with op.batch_alter_table("suite_settings") as batch:
            batch.drop_column("direct_play_devices")
    files = _columns("refiner_files")
    # refiner_files has foreign keys pointing at it (file logs), so drop in place rather than rebuild.
    for name in ("video_bit_depth", "audio_codecs"):
        if name in files:
            op.execute(f"ALTER TABLE refiner_files DROP COLUMN {name}")
