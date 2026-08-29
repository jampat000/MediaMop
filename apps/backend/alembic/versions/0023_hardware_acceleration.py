"""Hardware decode mode, per-vendor disables and ffmpeg strictness, per library

Refiner always stream-copies, so decode is rarely on the critical path today and no
encoder is invoked at all. This is modest for that reason — it exists because device
selection is a hard blocker the moment anything encodes (HDR to SDR, scaling, re-encoding
an oversized file, subtitle burn-in), and none of those can ship without it.

Defaults are ``off`` and ffmpeg's own ``normal`` strictness, which is exactly what
MediaMop does today by not passing the flags at all.

``hardware_disabled_vendors_csv`` exists because auto-detection picks the wrong device
often enough that FileFlows ships four explicit disable elements for it. Anything built
here needs the same escape hatch.

Revision ID: 0023_hardware_acceleration
Revises: 0022_output_collision_policy
Create Date: 2026-08-29 20:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0023_hardware_acceleration"
down_revision = "0022_output_collision_policy"
branch_labels = None
depends_on = None

_LIBRARY_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "hardware_decode_mode",
        sa.Column("hardware_decode_mode", sa.Text(), nullable=False, server_default="off"),
    ),
    ("hardware_device", sa.Column("hardware_device", sa.Text(), nullable=False, server_default="")),
    (
        "hardware_disabled_vendors_csv",
        sa.Column("hardware_disabled_vendors_csv", sa.Text(), nullable=False, server_default=""),
    ),
    ("ffmpeg_strictness", sa.Column("ffmpeg_strictness", sa.Text(), nullable=False, server_default="normal")),
)

#: The fallback is recorded on the file, so a slow pass is explained rather than
#: mysterious. Never a hard failure: a busy or absent device must not fail a file.
_FILE_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    ("hardware_method", sa.Column("hardware_method", sa.Text(), nullable=True)),
    (
        "hardware_fell_back_to_software",
        sa.Column("hardware_fell_back_to_software", sa.Boolean(), nullable=False, server_default="0"),
    ),
    ("hardware_reason", sa.Column("hardware_reason", sa.Text(), nullable=True)),
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


def upgrade() -> None:
    _add_missing("refiner_libraries", _LIBRARY_COLUMNS)
    _add_missing("refiner_files", _FILE_COLUMNS)


def downgrade() -> None:
    present = _columns("refiner_files")
    for name, _ in _FILE_COLUMNS:
        if name in present:
            op.drop_column("refiner_files", name)
    present = _columns("refiner_libraries")
    for name, _ in _LIBRARY_COLUMNS:
        if name in present:
            op.drop_column("refiner_libraries", name)
