"""Add per-library created and modified admission windows.

Revision ID: 0028_refiner_detection_windows
Revises: 0027_refiner_rejected_file_action
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0028_refiner_detection_windows"
down_revision = "0027_refiner_rejected_file_action"
branch_labels = None
depends_on = None


_COLUMNS = ("created_after", "created_before", "modified_after", "modified_before")


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("refiner_libraries")}
    for name in _COLUMNS:
        if name not in columns:
            op.add_column("refiner_libraries", sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("refiner_libraries")}
    for name in reversed(_COLUMNS):
        if name in columns:
            op.drop_column("refiner_libraries", name)
