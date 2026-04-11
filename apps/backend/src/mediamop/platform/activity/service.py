"""Persist and list activity events — no writes from Activity API routes in this pass.

Fetcher probe rows may be written only from the Fetcher operational overview service
(not from dashboard read paths). Fetcher failed-import activity is written from manual enqueue,
timed enqueue (when a new work row appears), Fetcher in-process job handlers (run start + outcome),
and the Fetcher recovery route.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.models import ActivityEvent

RECENT_DEFAULT_LIMIT = 50

_FETCHER_PROBE_SUPPRESS_MINUTES = 15
_LOGIN_FAILED_SUPPRESS_MINUTES = 2
_BOOTSTRAP_DENIED_SUPPRESS_SECONDS = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_activity_event(
    db: Session,
    *,
    event_type: str,
    module: str,
    title: str,
    detail: str | None = None,
) -> ActivityEvent:
    row = ActivityEvent(
        event_type=event_type,
        module=module,
        title=title,
        detail=detail,
    )
    db.add(row)
    db.flush()
    return row


def maybe_record_login_failed(db: Session, *, username: str) -> None:
    """One failed-login event per username per short window to limit brute-force noise."""

    cutoff = _utcnow() - timedelta(minutes=_LOGIN_FAILED_SUPPRESS_MINUTES)
    exists = db.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.event_type == C.AUTH_LOGIN_FAILED,
            ActivityEvent.detail == username,
            ActivityEvent.created_at >= cutoff,
        )
        .limit(1),
    ).first()
    if exists is not None:
        return
    record_activity_event(
        db,
        event_type=C.AUTH_LOGIN_FAILED,
        module="auth",
        title="Sign-in failed",
        detail=username,
    )


def maybe_record_bootstrap_denied(db: Session) -> None:
    """At most one bootstrap-denied row per minute (clustered abuse)."""

    cutoff = _utcnow() - timedelta(seconds=_BOOTSTRAP_DENIED_SUPPRESS_SECONDS)
    exists = db.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.event_type == C.AUTH_BOOTSTRAP_DENIED,
            ActivityEvent.created_at >= cutoff,
        )
        .limit(1),
    ).first()
    if exists is not None:
        return
    record_activity_event(
        db,
        event_type=C.AUTH_BOOTSTRAP_DENIED,
        module="auth",
        title="Bootstrap not allowed",
        detail="An admin account already exists.",
    )


def maybe_record_fetcher_probe_result(
    db: Session,
    *,
    target_display: str,
    probe_succeeded: bool,
) -> None:
    """Throttled persist of Fetcher /healthz outcome for the operational overview page only.

    Do not call from dashboard or other read-mostly snapshots (SQLite write pressure).
    """

    event_type = C.FETCHER_PROBE_SUCCEEDED if probe_succeeded else C.FETCHER_PROBE_FAILED
    title = "Fetcher health check OK" if probe_succeeded else "Fetcher health check failed"
    cutoff = _utcnow() - timedelta(minutes=_FETCHER_PROBE_SUPPRESS_MINUTES)
    last = db.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.module == "fetcher",
            ActivityEvent.event_type.in_((C.FETCHER_PROBE_SUCCEEDED, C.FETCHER_PROBE_FAILED)),
            ActivityEvent.created_at >= cutoff,
        )
        .order_by(desc(ActivityEvent.created_at))
        .limit(1),
    ).first()
    if last is not None:
        if last.event_type == event_type and (last.detail or "") == target_display:
            return
    record_activity_event(
        db,
        event_type=event_type,
        module="fetcher",
        title=title,
        detail=target_display,
    )


def count_activity_events_since(db: Session, *, since: datetime) -> int:
    n = db.scalar(select(func.count()).select_from(ActivityEvent).where(ActivityEvent.created_at >= since))
    return int(n or 0)


def get_latest_activity_event(db: Session) -> ActivityEvent | None:
    return db.scalars(select(ActivityEvent).order_by(desc(ActivityEvent.created_at)).limit(1)).first()


def get_latest_activity_event_id(db: Session) -> int | None:
    """Cheap freshness probe for SSE invalidation: max persisted activity id."""

    v = db.scalar(select(func.max(ActivityEvent.id)))
    return int(v) if v is not None else None


def get_latest_fetcher_probe_event(db: Session) -> ActivityEvent | None:
    return db.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.module == "fetcher",
            ActivityEvent.event_type.in_((C.FETCHER_PROBE_SUCCEEDED, C.FETCHER_PROBE_FAILED)),
        )
        .order_by(desc(ActivityEvent.created_at))
        .limit(1),
    ).first()


def list_recent_fetcher_probe_failures(
    db: Session,
    *,
    since: datetime,
    limit: int = 5,
) -> list[ActivityEvent]:
    """Persisted ``fetcher.probe_failed`` rows from ``since`` onward, newest first."""

    lim = max(1, min(limit, 20))
    return list(
        db.scalars(
            select(ActivityEvent)
            .where(
                ActivityEvent.module == "fetcher",
                ActivityEvent.event_type == C.FETCHER_PROBE_FAILED,
                ActivityEvent.created_at >= since,
            )
            .order_by(desc(ActivityEvent.created_at))
            .limit(lim),
        ).all(),
    )


def count_fetcher_probe_outcomes_since(db: Session, *, since: datetime) -> tuple[int, int]:
    """Count persisted Fetcher probe rows from ``since`` onward, split by outcome."""

    rows = db.execute(
        select(ActivityEvent.event_type, func.count())
        .where(
            ActivityEvent.module == "fetcher",
            ActivityEvent.event_type.in_((C.FETCHER_PROBE_SUCCEEDED, C.FETCHER_PROBE_FAILED)),
            ActivityEvent.created_at >= since,
        )
        .group_by(ActivityEvent.event_type),
    ).all()
    ok = 0
    failed = 0
    for event_type, n in rows:
        if event_type == C.FETCHER_PROBE_SUCCEEDED:
            ok = int(n)
        elif event_type == C.FETCHER_PROBE_FAILED:
            failed = int(n)
    return ok, failed


def list_recent_fetcher_probe_events(db: Session, *, limit: int = 8) -> list[ActivityEvent]:
    lim = max(1, min(limit, 20))
    return list(
        db.scalars(
            select(ActivityEvent)
            .where(
                ActivityEvent.module == "fetcher",
                ActivityEvent.event_type.in_((C.FETCHER_PROBE_SUCCEEDED, C.FETCHER_PROBE_FAILED)),
            )
            .order_by(desc(ActivityEvent.created_at))
            .limit(lim),
        ).all()
    )


def list_recent_activity_events(db: Session, *, limit: int = RECENT_DEFAULT_LIMIT) -> list[ActivityEvent]:
    lim = max(1, min(limit, 100))
    stmt = select(ActivityEvent).order_by(desc(ActivityEvent.created_at)).limit(lim)
    return list(db.scalars(stmt).all())
