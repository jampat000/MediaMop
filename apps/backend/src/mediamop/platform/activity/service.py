"""Persist and list activity events — no writes from Activity API routes in this pass."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc, event, func, or_, select
from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.live_stream import activity_latest_notifier
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.suite_settings.service import ensure_suite_settings_row

RECENT_DEFAULT_LIMIT = 50
_SYSTEM_MODULES = frozenset({"refiner", "pruner", "subber"})
_PENDING_ACTIVITY_IDS_INFO_KEY = "mediamop_activity_pending_latest_ids"

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
    suite = ensure_suite_settings_row(db)
    _maybe_prune_activity_rows_by_retention(db, keep_days=max(1, min(int(suite.log_retention_days), 3650)))
    row = ActivityEvent(
        event_type=event_type,
        module=module,
        title=title,
        detail=detail,
    )
    db.add(row)
    db.flush()
    pending_ids = db.info.setdefault(_PENDING_ACTIVITY_IDS_INFO_KEY, [])
    pending_ids.append(int(row.id))
    return row


def update_activity_event(
    db: Session,
    *,
    activity_id: int,
    event_type: str | None = None,
    title: str | None = None,
    detail: str | None = None,
) -> ActivityEvent | None:
    """Update an existing activity row and notify live Activity listeners after commit."""

    row = db.get(ActivityEvent, int(activity_id))
    if row is None:
        return None
    if event_type is not None:
        row.event_type = event_type
    if title is not None:
        row.title = title
    if detail is not None:
        row.detail = detail
    db.flush()
    pending_ids = db.info.setdefault(_PENDING_ACTIVITY_IDS_INFO_KEY, [])
    pending_ids.append(int(row.id))
    return row


@event.listens_for(Session, "after_commit")
def _publish_committed_activity_events(session: Session) -> None:
    pending_ids = session.info.pop(_PENDING_ACTIVITY_IDS_INFO_KEY, None)
    if pending_ids:
        activity_latest_notifier.notify(max(int(item) for item in pending_ids))


@event.listens_for(Session, "after_rollback")
def _clear_pending_activity_events(session: Session) -> None:
    session.info.pop(_PENDING_ACTIVITY_IDS_INFO_KEY, None)


def _maybe_prune_activity_rows_by_retention(db: Session, *, keep_days: int) -> None:
    cutoff = _utcnow() - timedelta(days=keep_days)
    db.execute(delete(ActivityEvent).where(ActivityEvent.created_at < cutoff))


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


def count_activity_events_since(db: Session, *, since: datetime) -> int:
    n = db.scalar(select(func.count()).select_from(ActivityEvent).where(ActivityEvent.created_at >= since))
    return int(n or 0)


def get_latest_activity_event(db: Session) -> ActivityEvent | None:
    return db.scalars(select(ActivityEvent).order_by(desc(ActivityEvent.created_at)).limit(1)).first()


def get_latest_activity_event_id(db: Session) -> int | None:
    """Cheap freshness probe for SSE invalidation: max persisted activity id."""

    v = db.scalar(select(func.max(ActivityEvent.id)))
    return int(v) if v is not None else None


def _filtered_activity_stmt(
    *,
    module: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    stmt = select(ActivityEvent)
    if module:
        normalized_module = module.strip().lower()
        if normalized_module == "system":
            stmt = stmt.where(ActivityEvent.module.not_in(_SYSTEM_MODULES))
        else:
            stmt = stmt.where(ActivityEvent.module == normalized_module)
    if event_type:
        stmt = stmt.where(ActivityEvent.event_type == event_type.strip())
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ActivityEvent.title.ilike(pattern),
                ActivityEvent.detail.ilike(pattern),
                ActivityEvent.event_type.ilike(pattern),
                ActivityEvent.module.ilike(pattern),
            )
        )
    if date_from is not None:
        stmt = stmt.where(ActivityEvent.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(ActivityEvent.created_at <= date_to)
    return stmt


def count_activity_events(
    db: Session,
    *,
    module: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> int:
    stmt = _filtered_activity_stmt(
        module=module,
        event_type=event_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
    ).with_only_columns(func.count()).order_by(None)
    return int(db.scalar(stmt) or 0)


def count_system_activity_events(
    db: Session,
    *,
    event_type: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> int:
    return count_activity_events(
        db,
        module="system",
        event_type=event_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )


def list_recent_activity_events(
    db: Session,
    *,
    limit: int = RECENT_DEFAULT_LIMIT,
    module: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[ActivityEvent]:
    lim = max(1, min(limit, 100))
    stmt = (
        _filtered_activity_stmt(
            module=module,
            event_type=event_type,
            search=search,
            date_from=date_from,
            date_to=date_to,
        )
        .order_by(desc(ActivityEvent.created_at))
        .limit(lim)
    )
    return list(db.scalars(stmt).all())
