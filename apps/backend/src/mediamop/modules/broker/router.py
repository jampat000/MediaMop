"""Broker HTTP routes under ``/api/v1/broker``."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.broker.broker_arr_connections_api import router as broker_arr_connections_router
from mediamop.modules.broker.broker_indexers_api import router as broker_indexers_router
from mediamop.modules.broker.broker_jobs_api import router as broker_jobs_router

router = APIRouter(prefix="/broker", tags=["broker"])
router.include_router(broker_indexers_router, prefix="/indexers")
router.include_router(broker_arr_connections_router, prefix="/connections")
router.include_router(broker_jobs_router)
