"""Store coarse, non-identifying labels for active sessions.

Revision ID: 0026_session_client_labels
Revises: 0025_drop_refiner_singletons
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0026_session_client_labels"
down_revision = "0025_drop_refiner_singletons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("user_sessions")}
    if "client_label" not in columns:
        op.add_column(
            "user_sessions",
            sa.Column("client_label", sa.String(length=80), nullable=False, server_default="Browser session"),
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("user_sessions")}
    if "client_label" in columns:
        op.drop_column("user_sessions", "client_label")
