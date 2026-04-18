"""Pruner scope: scheduled preview time window (days + hours).

Revision ID: 0037_pruner_scope_scheduled_preview_window
Revises: 0036_pruner_scope_preview_people_roles
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0037_pruner_scope_scheduled_preview_window"
down_revision: str | None = "0036_pruner_scope_preview_people_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "scheduled_preview_hours_limited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "scheduled_preview_days",
            sa.String(length=200),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "scheduled_preview_start",
            sa.String(length=5),
            nullable=False,
            server_default=sa.text("'00:00'"),
        ),
    )
    op.add_column(
        "pruner_scope_settings",
        sa.Column(
            "scheduled_preview_end",
            sa.String(length=5),
            nullable=False,
            server_default=sa.text("'23:59'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pruner_scope_settings", "scheduled_preview_end")
    op.drop_column("pruner_scope_settings", "scheduled_preview_start")
    op.drop_column("pruner_scope_settings", "scheduled_preview_days")
    op.drop_column("pruner_scope_settings", "scheduled_preview_hours_limited")
