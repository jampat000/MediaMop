"""Sidecar migration and original-timestamp preservation, per library

Refiner mirrored the watched-relative path under the output root and moved the video.
Nothing beside it came across — no .srt, no .nfo, no artwork, no .idx/.sub pair — and
then Movies cleanup ran rmtree on the release folder and TV did the same to a season
folder. Sidecars next to the source were destroyed rather than migrated, with no setting
that changed it.

``sidecar_patterns_csv`` defaults to the release-bundle set: subtitle formats including
the .idx/.sub pair, the metadata file, and artwork. That is a behaviour change, and a
deliberate one — the previous behaviour was destroying those files, and migrating a file
that would otherwise be deleted is strictly the safer direction.

The accompanying rule keeps it safe: a sidecar that is *not there* is not a failure, so a
release with no sidecars migrates nothing and blocks nothing. Only a sidecar that exists
and could not be copied blocks the source deletion, which is exactly the case where
proceeding would destroy the only copy.

``preserve_original_timestamps`` defaults off.

Revision ID: 0021_sidecar_migration
Revises: 0020_metadata_rules
Create Date: 2026-08-29 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "0021_sidecar_migration"
down_revision = "0020_metadata_rules"
branch_labels = None
depends_on = None

_DEFAULT_PATTERNS = ".srt,.ass,.ssa,.sub,.idx,.vtt,.nfo,.jpg,.png"

_LIBRARY_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    (
        "sidecar_patterns_csv",
        sa.Column("sidecar_patterns_csv", sa.Text(), nullable=False, server_default=_DEFAULT_PATTERNS),
    ),
    (
        "preserve_original_timestamps",
        sa.Column("preserve_original_timestamps", sa.Boolean(), nullable=False, server_default="0"),
    ),
)


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in set(inspector.get_table_names()):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    present = _columns("refiner_libraries")
    for name, column in _LIBRARY_COLUMNS:
        if present and name not in present:
            op.add_column("refiner_libraries", column)


def downgrade() -> None:
    present = _columns("refiner_libraries")
    for name, _ in _LIBRARY_COLUMNS:
        if name in present:
            op.drop_column("refiner_libraries", name)
