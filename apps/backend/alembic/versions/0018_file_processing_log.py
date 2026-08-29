"""A durable per-file processing record, with its own retention

Refiner computed every decision it made about a file and put it in an activity detail
payload — which then aged out under the suite's log retention along with everything else.
"Why did this file come out like that, three weeks ago" had no answer.

The two questions have different lifetimes. A suite log is for diagnosing the
application; a per-file record is for diagnosing a *file*, which somebody may only ask
about long after the fact. So the record gets its own table and its own retention.

One row per completed pass, not per file: a file that failed twice and then succeeded has
three things worth reading.

``refiner_operator_settings`` gains ``file_log_retention_days`` (90, and **0 means keep
forever**) and ``verbose_detection_logging`` (off — the switch to turn on while debugging
detection and off again afterwards).

Revision ID: 0018_file_processing_log
Revises: 0017_retry_and_sweeps
Create Date: 2026-08-29 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0018_file_processing_log"
down_revision = "0017_retry_and_sweeps"
branch_labels = None
depends_on = None

_OPERATOR_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "file_log_retention_days",
        sa.Column("file_log_retention_days", sa.Integer(), nullable=False, server_default="90"),
    ),
    (
        "verbose_detection_logging",
        sa.Column("verbose_detection_logging", sa.Boolean(), nullable=False, server_default="0"),
    ),
)


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if "refiner_file_logs" not in set(inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "refiner_file_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            # SET NULL, not CASCADE: forgetting a file from the Files screen must not
            # destroy the record of what was done to it. That is the opposite of why the
            # record exists.
            sa.Column("file_id", sa.Integer(), sa.ForeignKey("refiner_files.id", ondelete="SET NULL"), nullable=True),
            sa.Column(
                "library_id",
                sa.Integer(),
                sa.ForeignKey("refiner_libraries.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("relative_path", sa.Text(), nullable=False),
            sa.Column("library_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("outcome", sa.Text(), nullable=False, server_default=""),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_refiner_file_logs_path", "refiner_file_logs", ["relative_path"])
        op.create_index("ix_refiner_file_logs_recorded_at", "refiner_file_logs", ["recorded_at"])
        op.create_index("ix_refiner_file_logs_file", "refiner_file_logs", ["file_id"])

    present = _columns("refiner_operator_settings")
    for name, column in _OPERATOR_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_operator_settings", column)


def downgrade() -> None:
    present = _columns("refiner_operator_settings")
    for name, _ in _OPERATOR_COLUMNS:
        if name in present:
            op.drop_column("refiner_operator_settings", name)
    if "refiner_file_logs" in set(inspect(op.get_bind()).get_table_names()):
        op.drop_table("refiner_file_logs")
