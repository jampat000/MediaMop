"""Retry policy, classified failures, and the end of the dormant sweeps

Refiner **deletes source release folders after success**, and a file that failed was a
dead end: an activity row with a reason, and nothing else. The destructive path was
carefully engineered and the recovery path barely existed.

``refiner_libraries`` — retry policy, per library, because an operator watching a flaky
NAS wants different answers from one on local disk:

    ``max_attempts`` (3), ``retry_backoff_seconds`` (300),
    ``retry_execution_failures`` (on), ``retry_preflight_failures`` (off).

A file with no retainable audio will still have none in five minutes; an ffmpeg process
that died is the same file meeting a different world. Those are not the same failure and
the defaults say so.

``refiner_files`` — ``failure_class`` and ``failure_attempts``, so the reason a file
failed is something a policy can act on rather than a sentence to substring-match.

``refiner_operator_settings`` — the three sweeps stop being undocumented environment
variables:

    ``work_temp_stale_sweep_enabled`` defaults **on**. It reclaims MediaMop's own stale
    working files; a default install never doing that is the bug.

    ``failure_cleanup_enabled`` defaults **off**, deliberately. This sweep deletes source
    release folders after a terminal failure. Promoting it to a visible, documented
    setting is what the issue asks for; switching it on for every existing install
    without anybody choosing it is not, and "on by default where safe" is the qualifier
    that matters. It is now a setting an operator can find and turn on, which it never
    was before.

    ``keep_failed_work_files`` defaults off — opt-in retention so a failed remux can be
    inspected instead of swept.

Revision ID: 0017_retry_and_sweeps
Revises: 0016_runner_units
Create Date: 2026-08-29 14:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0017_retry_and_sweeps"
down_revision = "0016_runner_units"
branch_labels = None
depends_on = None

_LIBRARY_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("max_attempts", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")),
    (
        "retry_backoff_seconds",
        sa.Column("retry_backoff_seconds", sa.Integer(), nullable=False, server_default="300"),
    ),
    (
        "retry_execution_failures",
        sa.Column("retry_execution_failures", sa.Boolean(), nullable=False, server_default="1"),
    ),
    (
        "retry_preflight_failures",
        sa.Column("retry_preflight_failures", sa.Boolean(), nullable=False, server_default="0"),
    ),
)

_FILE_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("failure_class", sa.Column("failure_class", sa.Text(), nullable=True)),
    ("failure_attempts", sa.Column("failure_attempts", sa.Integer(), nullable=False, server_default="0")),
    ("next_retry_at", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True)),
)

_OPERATOR_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "work_temp_stale_sweep_enabled",
        sa.Column("work_temp_stale_sweep_enabled", sa.Boolean(), nullable=False, server_default="1"),
    ),
    (
        "failure_cleanup_enabled",
        sa.Column("failure_cleanup_enabled", sa.Boolean(), nullable=False, server_default="0"),
    ),
    (
        "keep_failed_work_files",
        sa.Column("keep_failed_work_files", sa.Boolean(), nullable=False, server_default="0"),
    ),
)


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _add_missing(table: str, columns: tuple[tuple[str, sa.Column], ...]) -> None:
    present = _columns(table)
    if not present:
        return
    for name, column in columns:
        if name not in present:
            op.add_column(table, column)


def _drop_present(table: str, names: tuple[str, ...]) -> None:
    present = _columns(table)
    for name in names:
        if name in present:
            op.drop_column(table, name)


def upgrade() -> None:
    _add_missing("refiner_libraries", _LIBRARY_COLUMNS)
    _add_missing("refiner_files", _FILE_COLUMNS)
    _add_missing("refiner_operator_settings", _OPERATOR_COLUMNS)


def downgrade() -> None:
    # Tolerant of a partially-applied upgrade: a downgrade that raises halfway leaves the
    # version row and the schema disagreeing, which is worse than what it was undoing.
    _drop_present("refiner_operator_settings", tuple(name for name, _ in _OPERATOR_COLUMNS))
    _drop_present("refiner_files", tuple(name for name, _ in _FILE_COLUMNS))
    _drop_present("refiner_libraries", tuple(name for name, _ in _LIBRARY_COLUMNS))
