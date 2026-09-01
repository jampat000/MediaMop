"""Add safe per-library cleanup for rejected Refiner files.

Revision ID: 0027_refiner_rejected_file_action
Revises: 0026_session_client_labels
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0027_refiner_rejected_file_action"
down_revision = "0026_session_client_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("refiner_libraries")}
    if "rejected_file_action" not in columns:
        op.add_column(
            "refiner_libraries",
            sa.Column("rejected_file_action", sa.Text(), nullable=False, server_default="leave"),
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("refiner_libraries")}
    if "rejected_file_action" in columns:
        op.drop_column("refiner_libraries", "rejected_file_action")
