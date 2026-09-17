"""Pruner scheduled auto-apply controls.

Revision ID: 0003_pruner_auto_apply_snapshot_limits
Revises: 0002_weir_schema_tip

Pruner moved to Deluno (#473) and ``0001`` no longer creates ``pruner_scope_settings`` on a
fresh database, so both directions do nothing when the table is absent. ``0036`` drops it
on databases that still have it.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0003_pruner_auto_apply_snapshot_limits"
down_revision: str | None = "0002_weir_schema_tip"


def _has_scope_table(bind: sa.engine.Connection) -> bool:
    return "pruner_scope_settings" in set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_scope_table(bind):
        return
    existing = {c["name"] for c in sa.inspect(bind).get_columns("pruner_scope_settings")}
    if "auto_apply_enabled" not in existing:
        op.add_column(
            "pruner_scope_settings",
            sa.Column("auto_apply_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if "max_deletes_per_run" not in existing:
        op.add_column(
            "pruner_scope_settings",
            sa.Column("max_deletes_per_run", sa.Integer(), nullable=False, server_default=sa.text("50")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_scope_table(bind):
        return
    existing = {c["name"] for c in sa.inspect(bind).get_columns("pruner_scope_settings")}
    with op.batch_alter_table("pruner_scope_settings") as batch:
        if "max_deletes_per_run" in existing:
            batch.drop_column("max_deletes_per_run")
        if "auto_apply_enabled" in existing:
            batch.drop_column("auto_apply_enabled")
