"""Create fetcher_jobs and move failed-import rows off refiner_jobs.

Revision ID: 0006_fetcher_jobs_split
Revises: 0005_failed_import_job_identity_strings
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_fetcher_jobs_split"
down_revision: Union[str, None] = "0005_failed_import_job_identity_strings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FAILED_IMPORT_JOB_KINDS = (
    "failed_import.radarr.cleanup_drive.v1",
    "failed_import.sonarr.cleanup_drive.v1",
)

_MIGRATION_LEASE_NOTE = (
    "p0_migration_0006: row was leased during fetcher_jobs split; reset to pending for retry. "
)


def upgrade() -> None:
    op.create_table(
        "fetcher_jobs",
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
        sa.PrimaryKeyConstraint("id", name="pk_fetcher_jobs"),
        sa.UniqueConstraint("dedupe_key", name="uq_fetcher_jobs_dedupe_key"),
    )
    op.create_index(
        "ix_fetcher_jobs_status_id",
        "fetcher_jobs",
        ["status", "id"],
        unique=False,
    )

    bind = op.get_bind()
    kinds_list = ",".join(f"'{k}'" for k in _FAILED_IMPORT_JOB_KINDS)
    # Copy rows; in-flight leased work becomes pending + cleared lease + audit note (retriable).
    bind.execute(
        sa.text(f"""
        INSERT INTO fetcher_jobs (
            id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at,
            attempt_count, max_attempts, last_error, created_at, updated_at
        )
        SELECT
            id,
            dedupe_key,
            job_kind,
            payload_json,
            CASE WHEN status = 'leased' THEN 'pending' ELSE status END,
            CASE WHEN status = 'leased' THEN NULL ELSE lease_owner END,
            CASE WHEN status = 'leased' THEN NULL ELSE lease_expires_at END,
            attempt_count,
            max_attempts,
            CASE
                WHEN status = 'leased' THEN
                    TRIM(COALESCE(last_error, '') || char(10) || :note)
                ELSE last_error
            END,
            created_at,
            updated_at
        FROM refiner_jobs
        WHERE job_kind IN ({kinds_list})
        """),
        {"note": _MIGRATION_LEASE_NOTE},
    )
    bind.execute(
        sa.text(f"DELETE FROM refiner_jobs WHERE job_kind IN ({kinds_list})"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    kinds_list = ",".join(f"'{k}'" for k in _FAILED_IMPORT_JOB_KINDS)
    bind.execute(
        sa.text(f"""
        INSERT INTO refiner_jobs (
            id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at,
            attempt_count, max_attempts, last_error, created_at, updated_at
        )
        SELECT
            id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at,
            attempt_count, max_attempts, last_error, created_at, updated_at
        FROM fetcher_jobs
        WHERE job_kind IN ({kinds_list})
        """),
    )
    bind.execute(sa.text(f"DELETE FROM fetcher_jobs WHERE job_kind IN ({kinds_list})"))

    op.drop_index("ix_fetcher_jobs_status_id", table_name="fetcher_jobs")
    op.drop_table("fetcher_jobs")
