"""Pruner HTTP routes — product APIs mount here when job families ship (Phase 2+)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["pruner"])
