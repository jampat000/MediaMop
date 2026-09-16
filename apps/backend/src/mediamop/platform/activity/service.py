"""Persist and list activity events — no writes from Activity API routes in this pass."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import desc, event, func, or_, select
from sqlalchemy.orm import Session

from mediamop.platform.activity import constants as C
from mediamop.platform.activity.classify import classify_activity
from mediamop.platform.activity.live_stream import activity_latest_notifier
from mediamop.platform.activity.models import ActivityEvent

RECENT_DEFAULT_LIMIT = 50
_SYSTEM_MODULES = frozenset({"refiner", "pruner"})
_PENDING_ACTIVITY_IDS_INFO_KEY = "mediamop_activity_pending_latest_ids"

_LOGIN_FAILED_SUPPRESS_MINUTES = 2
_BOOTSTRAP_DENIED_SUPPRESS_SECONDS = 60


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _apply_facts(row: ActivityEvent) -> None:
    facts = classify_activity(event_type=row.event_type, detail=row.detail)
    row.trigger = facts.trigger
    row.result = facts.result
    row.library_id = facts.library_id
    row.relative_path = facts.relative_path
    row.run_key = facts.run_key


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
    _apply_facts(row)
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
    _apply_facts(row)
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
    trigger: str | None = None,
    result: str | None = None,
    library_id: int | None = None,
    file: str | None = None,
):
    stmt = select(ActivityEvent)
    if trigger:
        stmt = stmt.where(ActivityEvent.trigger == trigger.strip().lower())
    if result:
        stmt = stmt.where(ActivityEvent.result == result.strip().lower())
    if library_id is not None:
        stmt = stmt.where(ActivityEvent.library_id == int(library_id))
    if file:
        # A file's whole history: its path, or its name anywhere in a path.
        needle = file.strip()
        stmt = stmt.where(ActivityEvent.relative_path.ilike(f"%{needle}%"))
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
    trigger: str | None = None,
    result: str | None = None,
    library_id: int | None = None,
    file: str | None = None,
) -> int:
    stmt = (
        _filtered_activity_stmt(
            module=module,
            event_type=event_type,
            search=search,
            date_from=date_from,
            date_to=date_to,
            trigger=trigger,
            result=result,
            library_id=library_id,
            file=file,
        )
        .with_only_columns(func.count())
        .order_by(None)
    )
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
    before_id: int | None = None,
    trigger: str | None = None,
    result: str | None = None,
    library_id: int | None = None,
    file: str | None = None,
) -> list[ActivityEvent]:
    lim = max(1, min(limit, 100))
    stmt = (
        _filtered_activity_stmt(
            module=module,
            event_type=event_type,
            search=search,
            date_from=date_from,
            date_to=date_to,
            trigger=trigger,
            result=result,
            library_id=library_id,
            file=file,
        )
        .order_by(desc(ActivityEvent.created_at))
        .limit(lim)
    )
    if before_id is not None:
        stmt = stmt.where(ActivityEvent.id < int(before_id))
    return list(db.scalars(stmt).all())


EXPORT_MAX_ROWS = 50_000


def list_activity_events_for_export(
    db: Session,
    *,
    module: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    trigger: str | None = None,
    result: str | None = None,
    library_id: int | None = None,
    file: str | None = None,
) -> list[ActivityEvent]:
    """Every matching event, oldest first, up to ``EXPORT_MAX_ROWS``."""

    stmt = (
        _filtered_activity_stmt(
            module=module,
            event_type=event_type,
            search=search,
            date_from=date_from,
            date_to=date_to,
            trigger=trigger,
            result=result,
            library_id=library_id,
            file=file,
        )
        .order_by(ActivityEvent.created_at, ActivityEvent.id)
        .limit(EXPORT_MAX_ROWS)
    )
    return list(db.scalars(stmt).all())


def get_oldest_activity_event_at(db: Session) -> datetime | None:
    return db.scalar(select(func.min(ActivityEvent.created_at)))


def prune_activity_events(db: Session, *, retention_days: int, now: datetime | None = None) -> int:
    """Remove events older than ``retention_days``. Zero or less keeps everything."""

    if retention_days <= 0:
        return 0
    cutoff = (now or _utcnow()) - timedelta(days=int(retention_days))
    result = db.execute(sa_delete(ActivityEvent).where(ActivityEvent.created_at < cutoff))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _file_history_filter(*, library_id: int | None, relative_path: str):
    clause = ActivityEvent.relative_path == relative_path.strip()
    if library_id is not None:
        # Events written before a library was recorded on them still belong to this file.
        clause = clause & or_(ActivityEvent.library_id == int(library_id), ActivityEvent.library_id.is_(None))
    return clause


def count_file_activity_history(db: Session, *, library_id: int | None, relative_path: str) -> int:
    stmt = (
        select(func.count())
        .select_from(ActivityEvent)
        .where(_file_history_filter(library_id=library_id, relative_path=relative_path))
    )
    return int(db.scalar(stmt) or 0)


def delete_file_activity_history(db: Session, *, library_id: int | None, relative_path: str) -> int:
    result = db.execute(
        sa_delete(ActivityEvent).where(_file_history_filter(library_id=library_id, relative_path=relative_path))
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
