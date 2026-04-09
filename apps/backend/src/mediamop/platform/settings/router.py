"""Settings HTTP API — not mounted in Phase 3 (no routes; avoids implying a finished Settings API)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
# Intentionally no routes. Include under /api/v1 when contracts and persistence exist.
