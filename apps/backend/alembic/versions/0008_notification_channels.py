"""Add notification_channels table for outbound job event webhooks

Revision ID: 0008_notification_channels
Revises: 0007_indexes_and_retry_backoff
Create Date: 2026-05-12 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0008_notification_channels"
down_revision = "0007_indexes_and_retry_backoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "notification_channels" not in insp.get_table_names():
        op.create_table(
            "notification_channels",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("label", sa.Text, nullable=False),
            sa.Column("provider", sa.Text, nullable=False),
            sa.Column("url", sa.Text, nullable=False),
            sa.Column("events_json", sa.Text, nullable=False, server_default='["job_failed"]'),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if "notification_channels" in insp.get_table_names():
        op.drop_table("notification_channels")
