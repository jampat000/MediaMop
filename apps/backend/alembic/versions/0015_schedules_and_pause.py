"""A 7x24 schedule grid per library, and a suite-wide pause

Refiner's schedule gated **enqueue** only. Once a job was queued it ran to completion
regardless of the window, so a 4K remux started two minutes before closing ran into the
morning — the outcome the window existed to prevent. And there was no pause of any kind
on a tool whose whole job is sustained disk and CPU load on a machine someone is using.

``refiner_libraries.schedule_grid``
    7 days x 96 quarter-hours as 672 characters of ``0``/``1``. Empty means no
    restriction. Backfilled from each library's existing days/start/end so an upgrade
    changes nothing about when work runs; the trio stays as the fallback for any row this
    could not express, and is not dropped here.

``suite_settings.processing_paused`` / ``processing_paused_until`` / ``scan_while_paused``
    Pause lives on the suite rather than on Refiner so Pruner can honour the same switch
    later instead of growing a second one beside it. ``scan_while_paused`` defaults on,
    because the useful pause is "stop working on files", not "stop noticing them".

Revision ID: 0015_schedules_and_pause
Revises: 0014_refiner_watcher
Create Date: 2026-08-29 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0015_schedules_and_pause"
down_revision = "0014_refiner_watcher"
branch_labels = None
depends_on = None

_SUITE_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("processing_paused", sa.Column("processing_paused", sa.Boolean(), nullable=False, server_default="0")),
    (
        "processing_paused_until",
        sa.Column("processing_paused_until", sa.DateTime(timezone=True), nullable=True),
    ),
    ("scan_while_paused", sa.Column("scan_while_paused", sa.Boolean(), nullable=False, server_default="1")),
)


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    present = _columns("suite_settings")
    for name, column in _SUITE_COLUMNS:
        if present and name not in present:
            op.add_column("suite_settings", column)

    present = _columns("refiner_libraries")
    if not present:
        return
    if "schedule_grid" not in present:
        op.add_column(
            "refiner_libraries",
            sa.Column("schedule_grid", sa.Text(), nullable=False, server_default=""),
        )

    # Backfill from the window each library already has, so an upgrade preserves exactly
    # when work runs. A library with no hour limit keeps an empty grid, which means no
    # restriction — not an all-zero grid, which would mean never.
    from mediamop.modules.refiner.refiner_schedule_grid import grid_from_days_and_times

    rows = bind.execute(
        sa.text("SELECT id, schedule_hours_limited, schedule_days, schedule_start, schedule_end FROM refiner_libraries")
    ).fetchall()
    for row in rows:
        if not row[1]:
            continue
        grid = grid_from_days_and_times(
            days=row[2] or "",
            start=row[3] or "00:00",
            end=row[4] or "23:59",
        )
        if not grid:
            continue
        bind.execute(
            sa.text("UPDATE refiner_libraries SET schedule_grid = :grid WHERE id = :id"),
            {"grid": grid, "id": row[0]},
        )


def downgrade() -> None:
    op.drop_column("refiner_libraries", "schedule_grid")
    for name, _ in _SUITE_COLUMNS:
        op.drop_column("suite_settings", name)
