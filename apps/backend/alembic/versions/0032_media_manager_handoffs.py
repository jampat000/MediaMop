"""A durable record of each hand-off a media manager gave Weir (#480).

Deluno stops timing hand-offs out and asks Weir about each one instead (Deluno#511). The
hand-off id used to live only on a job row, and job rows are pruned, so the answer has to live
somewhere that outlasts them.

Revision ID: 0032_media_manager_handoffs
Revises: 0031_refiner_failure_policy
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0032_media_manager_handoffs"
down_revision = "0031_refiner_failure_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "media_manager_handoffs" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "media_manager_handoffs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("handoff_id", sa.Text(), nullable=False),
        sa.Column(
            "library_id",
            sa.Integer(),
            sa.ForeignKey("refiner_libraries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_key", "handoff_id", name="uq_media_manager_handoffs_source_id"),
    )


def downgrade() -> None:
    if "media_manager_handoffs" in inspect(op.get_bind()).get_table_names():
        op.drop_table("media_manager_handoffs")
