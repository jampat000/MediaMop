"""Refiner file states — the reasons a file is deliberately not being processed

Refiner could say a job was pending, leased, completed or failed. It could not say
"disabled", "on hold", "out of schedule" or "blocked upstream", so every deliberate
decision *not* to process a file was invisible to the operator.

Creates ``refiner_files``. Nothing is backfilled: a file's state is whatever the next
scan concludes, and inventing history for files nobody has looked at yet would be
inventing reasons too.

Revision ID: 0012_refiner_file_states
Revises: 0011_refiner_libraries
Create Date: 2026-08-28 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0012_refiner_file_states"
down_revision = "0011_refiner_libraries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "refiner_files" in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "refiner_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "library_id",
            sa.Integer(),
            sa.ForeignKey("refiner_libraries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="unprocessed"),
        sa.Column("status_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("blocked_by_connection", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("library_id", "relative_path", name="uq_refiner_files_library_path"),
    )
    op.create_index("ix_refiner_files_status", "refiner_files", ["status"])
    op.create_index("ix_refiner_files_library_status", "refiner_files", ["library_id", "status"])


def downgrade() -> None:
    op.drop_table("refiner_files")
