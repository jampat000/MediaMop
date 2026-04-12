"""Rename Refiner library audit pass identifiers to supplied payload evaluation (truth alignment).

``refiner.library.audit_pass.v1`` overstated behavior (no library scan or *arr calls). Persisted
``refiner_jobs`` rows and activity ``event_type`` values are updated in place.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_refiner_supplied_payload_evaluation_rename"
down_revision: str | None = "0007_fetcher_arr_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE refiner_jobs SET job_kind = 'refiner.supplied_payload_evaluation.v1' "
            "WHERE job_kind = 'refiner.library.audit_pass.v1'",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE refiner_jobs SET dedupe_key = 'refiner.supplied_payload_evaluation:v1' "
            "WHERE dedupe_key = 'refiner.library.audit_pass:v1'",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE activity_events SET event_type = 'refiner.supplied_payload_evaluation_completed' "
            "WHERE event_type = 'refiner.library_audit_pass_completed'",
        ),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE refiner_jobs SET job_kind = 'refiner.library.audit_pass.v1' "
            "WHERE job_kind = 'refiner.supplied_payload_evaluation.v1'",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE refiner_jobs SET dedupe_key = 'refiner.library.audit_pass:v1' "
            "WHERE dedupe_key = 'refiner.supplied_payload_evaluation:v1'",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE activity_events SET event_type = 'refiner.library_audit_pass_completed' "
            "WHERE event_type = 'refiner.supplied_payload_evaluation_completed'",
        ),
    )
