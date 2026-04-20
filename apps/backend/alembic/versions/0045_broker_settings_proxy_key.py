"""Broker settings row for unified Torznab/Newznab proxy API key.

Revision ID: 0045_broker_settings_proxy_key
Revises: 0044_broker_foundation
Create Date: 2026-04-20
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0045_broker_settings_proxy_key"
down_revision: str | None = "0044_broker_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proxy_api_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.get_bind().execute(
        sa.text("INSERT INTO broker_settings (id, proxy_api_key) VALUES (1, :k)"),
        {"k": str(uuid.uuid4())},
    )


def downgrade() -> None:
    op.drop_table("broker_settings")
