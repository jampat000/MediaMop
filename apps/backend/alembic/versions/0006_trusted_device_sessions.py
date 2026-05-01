"""add trusted-device flag to user sessions

Revision ID: 0006_trusted_device_sessions
Revises: 0005_refiner_guardrail_settings
Create Date: 2026-05-01 09:58:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0006_trusted_device_sessions"
down_revision = "0005_refiner_guardrail_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("user_sessions")}
    if "is_trusted_device" not in columns:
        op.add_column(
            "user_sessions",
            sa.Column(
                "is_trusted_device",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("user_sessions")}
    if "is_trusted_device" in columns:
        op.drop_column("user_sessions", "is_trusted_device")
