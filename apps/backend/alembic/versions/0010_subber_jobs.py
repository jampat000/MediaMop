"""subber_jobs table for Subber-local durable queue (claim/lease).

Revision ID: 0010_subber_jobs
Revises: 0009_trimmer_jobs
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010_subber_jobs"
down_revision: str | None = "0009_trimmer_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subber_jobs",
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
        sa.PrimaryKeyConstraint("id", name="pk_subber_jobs"),
        sa.UniqueConstraint("dedupe_key", name="uq_subber_jobs_dedupe_key"),
    )
    op.create_index(
        "ix_subber_jobs_status_id",
        "subber_jobs",
        ["status", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_subber_jobs_status_id", table_name="subber_jobs")
    op.drop_table("subber_jobs")
