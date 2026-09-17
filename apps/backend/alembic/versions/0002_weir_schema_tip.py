"""Schema chain tip (no-op).

Keeps a linear Alembic history so ``_strictly_behind_head`` can upgrade from the initial
revision to head during API startup tests.
"""

from __future__ import annotations

revision: str = "0002_weir_schema_tip"
down_revision: str | None = "0001_weir_initial_schema"


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
