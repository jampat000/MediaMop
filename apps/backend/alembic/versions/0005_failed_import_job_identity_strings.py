"""Rewrite persisted failed-import cleanup drive job_kind and dedupe_key away from refiner.*.

Revision ID: 0005_failed_import_job_identity_strings
Revises: 0004_fetcher_failed_import_cleanup_policy
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005_failed_import_job_identity_strings"
down_revision: Union[str, None] = "0004_fetcher_failed_import_cleanup_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Transitional: failed_import.* rows still live on ``refiner_jobs`` here; revision 0006 moves
    # them to ``fetcher_jobs``. Current app code never enqueues failed_import.* onto refiner_jobs.
    # Radarr failed-import cleanup drive (Fetcher-owned lane; historical strings used refiner.*).
    op.execute(
        "UPDATE refiner_jobs SET job_kind = 'failed_import.radarr.cleanup_drive.v1' "
        "WHERE job_kind = 'refiner.radarr.failed_import_cleanup_drive.v1'",
    )
    op.execute(
        "UPDATE refiner_jobs SET dedupe_key = 'failed_import.radarr.cleanup_drive:v1' "
        "WHERE dedupe_key = 'refiner.radarr.failed_import_cleanup_drive:v1'",
    )
    op.execute(
        "UPDATE refiner_jobs SET job_kind = 'failed_import.sonarr.cleanup_drive.v1' "
        "WHERE job_kind = 'refiner.sonarr.failed_import_cleanup_drive.v1'",
    )
    op.execute(
        "UPDATE refiner_jobs SET dedupe_key = 'failed_import.sonarr.cleanup_drive:v1' "
        "WHERE dedupe_key = 'refiner.sonarr.failed_import_cleanup_drive:v1'",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE refiner_jobs SET job_kind = 'refiner.radarr.failed_import_cleanup_drive.v1' "
        "WHERE job_kind = 'failed_import.radarr.cleanup_drive.v1'",
    )
    op.execute(
        "UPDATE refiner_jobs SET dedupe_key = 'refiner.radarr.failed_import_cleanup_drive:v1' "
        "WHERE dedupe_key = 'failed_import.radarr.cleanup_drive:v1'",
    )
    op.execute(
        "UPDATE refiner_jobs SET job_kind = 'refiner.sonarr.failed_import_cleanup_drive.v1' "
        "WHERE job_kind = 'failed_import.sonarr.cleanup_drive.v1'",
    )
    op.execute(
        "UPDATE refiner_jobs SET dedupe_key = 'refiner.sonarr.failed_import_cleanup_drive:v1' "
        "WHERE dedupe_key = 'failed_import.sonarr.cleanup_drive:v1'",
    )
