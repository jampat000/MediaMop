"""Drop legacy trimmer_jobs; create pruner_jobs durable queue.

Revision ID: 0025_pruner_jobs_drop_trimmer_jobs
Revises: 0024_refiner_path_watched_folder_poll_intervals
Create Date: 2026-04-17

Historical note: ``0009_trimmer_jobs`` remains in the Alembic chain unchanged.
This revision supersedes the runtime table for new databases and upgrades.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0025_pruner_jobs_drop_trimmer_jobs"
down_revision: str | None = "0024_refiner_path_watched_folder_poll_intervals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("trimmer_jobs")
    op.create_table(
        "pruner_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dedupe_key", sa.String(length=512), nullable=False),
        sa.Column("job_kind", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pruner_jobs"),
        sa.UniqueConstraint("dedupe_key", name="uq_pruner_jobs_dedupe_key"),
    )
    op.create_index(
        "ix_pruner_jobs_status_id",
        "pruner_jobs",
        ["status", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pruner_jobs_status_id", table_name="pruner_jobs")
    op.drop_table("pruner_jobs")
    op.create_table(
        "trimmer_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dedupe_key", sa.String(length=512), nullable=False),
        sa.Column("job_kind", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trimmer_jobs"),
        sa.UniqueConstraint("dedupe_key", name="uq_trimmer_jobs_dedupe_key"),
    )
    op.create_index(
        "ix_trimmer_jobs_status_id",
        "trimmer_jobs",
        ["status", "id"],
        unique=False,
    )
