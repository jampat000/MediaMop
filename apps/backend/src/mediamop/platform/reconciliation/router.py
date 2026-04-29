"""Operator API for safe filesystem/database reconciliation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mediamop.api.deps import DbSessionDep
from mediamop.platform.activity.service import record_activity_event
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.reconciliation.service import build_reconciliation_report, repair_reconciliation_issue

router = APIRouter(prefix="/system/reconciliation", tags=["system-reconciliation"])


class ReconciliationRepairIn(BaseModel):
    action: str = Field(min_length=1, max_length=100)
    db_id: int | None = Field(default=None, ge=1)
    path: str | None = Field(default=None, max_length=2000)
    confirm: bool = False


@router.get("")
def get_reconciliation_report(
    db: DbSessionDep,
    _user: RequireOperatorDep,
):
    """Return non-mutating filesystem/database reconciliation findings."""

    return build_reconciliation_report(db)


@router.post("/repair")
def post_reconciliation_repair(
    body: ReconciliationRepairIn,
    db: DbSessionDep,
    _user: RequireOperatorDep,
):
    """Apply one explicit safe repair action."""

    try:
        result = repair_reconciliation_issue(
            db,
            action=body.action,
            db_id=body.db_id,
            path=body.path,
            confirm=body.confirm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_activity_event(
        db,
        event_type="system.reconciliation.repair",
        module="system",
        title="System repair action completed" if result.get("applied") else "System repair action skipped",
        detail=f"{body.action}: {result.get('message', '')}",
    )
    return result
