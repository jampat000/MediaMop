"""Broker module foundation: indexers, *arr connections, durable jobs queue.

Revision ID: 0044_broker_foundation
Revises: 0043_subber_providers_nullable_priority_new_providers
Create Date: 2026-04-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0044_broker_foundation"
down_revision: str | None = "0043_subber_providers_nullable_priority_new_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_indexers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("protocol", sa.Text(), nullable=False),
        sa.Column(
            "privacy",
            sa.Text(),
            server_default=sa.text("'public'"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("api_key", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "enabled",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("25"),
            nullable=False,
        ),
        sa.Column(
            "categories",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "tags",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Integer(), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_broker_indexers"),
        sa.UniqueConstraint("slug", name="uq_broker_indexers_slug"),
    )

    op.create_table(
        "broker_arr_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("arr_type", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("api_key", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "sync_mode",
            sa.Text(),
            server_default=sa.text("'full'"),
            nullable=False,
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_ok", sa.Integer(), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("last_manual_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_manual_sync_ok", sa.Integer(), nullable=True),
        sa.Column("indexer_fingerprint", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_broker_arr_connections"),
        sa.UniqueConstraint("arr_type", name="uq_broker_arr_connections_arr_type"),
    )

    op.create_table(
        "broker_jobs",
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
        sa.PrimaryKeyConstraint("id", name="pk_broker_jobs"),
        sa.UniqueConstraint("dedupe_key", name="uq_broker_jobs_dedupe_key"),
    )
    op.create_index(
        "ix_broker_jobs_status_id",
        "broker_jobs",
        ["status", "id"],
        unique=False,
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO broker_arr_connections (arr_type, url, api_key, sync_mode) "
            "VALUES ('sonarr', '', '', 'full'), ('radarr', '', '', 'full')"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_broker_jobs_status_id", table_name="broker_jobs")
    op.drop_table("broker_jobs")
    op.drop_table("broker_arr_connections")
    op.drop_table("broker_indexers")
