"""Runner units, job priority, and the resolution a file was measured at

``max_concurrent_files`` treated a 700 MB SD rip and a 60 GB 4K remux as the same unit of
work. A machine sized for two of the latter sits idle under six of the former, and one
sized for six of the former is overwhelmed by two of the latter. The count was never
protecting the thing it appeared to protect.

``refiner_operator_settings``
    ``runner_capacity`` plus a cost per resolution class. Capacity is migrated from the
    saved ``max_concurrent_files`` one-for-one, so with the shipped costs the same number
    of expensive files run at once. Smaller files now cost nothing and run alongside.

``refiner_jobs``
    ``runner_cost`` — what this job spends, fixed at enqueue so the claim is a comparison
    rather than a join. ``priority`` — higher first, seeded from the library and raised by
    "move to top".

``refiner_files``
    ``video_width`` / ``video_height`` — recorded after a pass, read at the next enqueue.
    Null costs the ``undetermined`` weight rather than a guess. Width decides the class:
    1920x800 is a scope crop of a 1080p master, and height alone cannot tell it from
    1280x720.

Shipped costs match the observed FileFlows values: SD and 720p free, 1080p and 4K one
unit each, undetermined free.

Revision ID: 0016_runner_units
Revises: 0015_schedules_and_pause
Create Date: 2026-08-29 13:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0016_runner_units"
down_revision = "0015_schedules_and_pause"
branch_labels = None
depends_on = None

_OPERATOR_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("runner_capacity", sa.Column("runner_capacity", sa.Integer(), nullable=False, server_default="4")),
    ("runner_cost_sd", sa.Column("runner_cost_sd", sa.Integer(), nullable=False, server_default="0")),
    ("runner_cost_720p", sa.Column("runner_cost_720p", sa.Integer(), nullable=False, server_default="0")),
    ("runner_cost_1080p", sa.Column("runner_cost_1080p", sa.Integer(), nullable=False, server_default="1")),
    ("runner_cost_4k", sa.Column("runner_cost_4k", sa.Integer(), nullable=False, server_default="1")),
    (
        "runner_cost_undetermined",
        sa.Column("runner_cost_undetermined", sa.Integer(), nullable=False, server_default="0"),
    ),
)

_JOB_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("runner_cost", sa.Column("runner_cost", sa.Integer(), nullable=False, server_default="0")),
    ("priority", sa.Column("priority", sa.Integer(), nullable=False, server_default="0")),
)


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    present = _columns("refiner_operator_settings")
    for name, column in _OPERATOR_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_operator_settings", column)

    present = _columns("refiner_jobs")
    for name, column in _JOB_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_jobs", column)

    present = _columns("refiner_files")
    for name in ("video_width", "video_height"):
        if present and name not in present:
            op.add_column("refiner_files", sa.Column(name, sa.Integer(), nullable=True))

    # Preserve the effective concurrency an operator already chose.
    if _columns("refiner_operator_settings"):
        from mediamop.modules.refiner.refiner_runner_units import capacity_from_legacy_concurrency

        saved = bind.execute(
            sa.text("SELECT max_concurrent_files FROM refiner_operator_settings WHERE id = 1")
        ).fetchone()
        if saved is not None:
            bind.execute(
                sa.text("UPDATE refiner_operator_settings SET runner_capacity = :cap WHERE id = 1"),
                {"cap": capacity_from_legacy_concurrency(int(saved[0] or 1))},
            )


def downgrade() -> None:
    # Tolerant of a partially-applied upgrade. A downgrade that raises halfway leaves the
    # version row saying one thing and the schema saying another, which is worse than the
    # state it was trying to undo.
    present = _columns("refiner_files")
    for name in ("video_height", "video_width"):
        if name in present:
            op.drop_column("refiner_files", name)
    present = _columns("refiner_jobs")
    for name, _ in _JOB_COLUMNS:
        if name in present:
            op.drop_column("refiner_jobs", name)
    present = _columns("refiner_operator_settings")
    for name, _ in _OPERATOR_COLUMNS:
        if name in present:
            op.drop_column("refiner_operator_settings", name)
