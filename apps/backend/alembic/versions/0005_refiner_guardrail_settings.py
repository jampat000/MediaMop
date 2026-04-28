"""Refiner intake and disk guardrail settings.

Revision ID: 0005_refiner_guardrail_settings
Revises: 0004_pruner_uniqueness_constraints
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0005_refiner_guardrail_settings"
down_revision: str | None = "0004_pruner_uniqueness_constraints"


def _columns(table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    cols = _columns("refiner_operator_settings")
    if "refiner_min_input_file_size_mb" not in cols:
        op.add_column(
            "refiner_operator_settings",
            sa.Column("refiner_min_input_file_size_mb", sa.Integer(), nullable=False, server_default="50"),
        )
    if "minimum_free_disk_space_mb" not in cols:
        op.add_column(
            "refiner_operator_settings",
            sa.Column("minimum_free_disk_space_mb", sa.Integer(), nullable=False, server_default="5120"),
        )


def downgrade() -> None:
    cols = _columns("refiner_operator_settings")
    if "minimum_free_disk_space_mb" in cols:
        op.drop_column("refiner_operator_settings", "minimum_free_disk_space_mb")
    if "refiner_min_input_file_size_mb" in cols:
        op.drop_column("refiner_operator_settings", "refiner_min_input_file_size_mb")
