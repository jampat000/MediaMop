"""Create, edit, reorder and delete Refiner libraries and rule sets.

Two refusals carry the weight here, and both exist because the alternative is silent
damage rather than an error message:

- **A library with queued or running work cannot be deleted.** Those jobs resolve their
  paths *from the library*. Deleting it would leave a remux mid-flight with nothing to
  resolve against, and Refiner deletes source folders on the strength of those paths.
- **A rule set still referenced cannot be deleted.** ADR-0014 §3 makes a rule set a
  shared object precisely so two libraries can point at one; a cascade would silently
  strip audio and subtitle handling from whatever else was using it.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_library_model import (
    REFINER_MEDIA_SCOPES,
    RefinerLibraryManagerLinkRow,
    RefinerLibraryRow,
    RefinerRuleSetRow,
)
from mediamop.modules.refiner.refiner_library_service import (
    list_libraries,
    manager_connection_ids_for,
)
from mediamop.modules.refiner.refiner_schedule_grid import ScheduleGridError, normalize_grid
from mediamop.modules.refiner.refiner_track_sorters import (
    TrackSorterError,
    dump_sorters,
    preset_sorters,
    validate_sorters,
)
from mediamop.platform.media_managers.connection_model import MediaManagerConnectionRow

_ACTIVE_JOB_STATUSES = (RefinerJobStatus.PENDING.value, RefinerJobStatus.LEASED.value)


class RefinerLibraryError(ValueError):
    """A library or rule set could not be saved or removed, with an operator-readable reason."""


def active_job_count_for_library(session: Session, library: RefinerLibraryRow) -> int:
    """Queued or leased Refiner jobs belonging to this library.

    Counts a payload's ``library_id`` and, for the seeded library of a scope, payloads
    that predate libraries and carry only ``media_scope`` — those resolve here too, so
    they are just as stranded by a delete.
    """

    seeded_for_scope = next(
        (row for row in list_libraries(session) if row.media_scope == library.media_scope),
        None,
    )
    is_seeded = seeded_for_scope is not None and seeded_for_scope.id == library.id

    count = 0
    for job in session.scalars(select(RefinerJob).where(RefinerJob.status.in_(_ACTIVE_JOB_STATUSES))):
        raw = job.payload_json
        if not raw or not str(raw).strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        payload_library_id = data.get("library_id")
        if isinstance(payload_library_id, int) and not isinstance(payload_library_id, bool):
            if payload_library_id == library.id:
                count += 1
            continue
        if is_seeded:
            scope = (data.get("media_scope") or "movie").strip().lower()
            scope = "tv" if scope == "tv" else "movie"
            if scope == library.media_scope:
                count += 1
    return count


def _validate_scope(media_scope: str) -> str:
    scope = (media_scope or "").strip().lower()
    if scope not in REFINER_MEDIA_SCOPES:
        raise RefinerLibraryError(
            f"Unknown media scope {media_scope!r}. Use one of: {', '.join(REFINER_MEDIA_SCOPES)}."
        )
    return scope


def _validate_name(session: Session, name: str, *, exclude_id: int | None = None) -> str:
    label = (name or "").strip()
    if not label:
        raise RefinerLibraryError("Give the library a name so you can tell it apart later.")
    clash = session.scalars(select(RefinerLibraryRow).where(RefinerLibraryRow.name == label)).first()
    if clash is not None and clash.id != exclude_id:
        raise RefinerLibraryError(f"A library named {label!r} already exists.")
    return label


def _validate_manager_connections(session: Session, connection_ids: list[int]) -> list[int]:
    unique = sorted({int(c) for c in connection_ids})
    if not unique:
        return []
    found = {
        row.id
        for row in session.scalars(select(MediaManagerConnectionRow).where(MediaManagerConnectionRow.id.in_(unique)))
    }
    missing = [c for c in unique if c not in found]
    if missing:
        raise RefinerLibraryError(
            f"No media manager connection with id {missing[0]}. Add the connection first, then link it."
        )
    return unique


def _validate_rule_set(session: Session, rule_set_id: int | None) -> int | None:
    if rule_set_id is None:
        return None
    if session.get(RefinerRuleSetRow, rule_set_id) is None:
        raise RefinerLibraryError(f"No rule set with id {rule_set_id}.")
    return rule_set_id


def _apply_fields(session: Session, row: RefinerLibraryRow, body: object) -> None:
    for field in (
        "enabled",
        "watched_folder",
        "work_folder",
        "output_folder",
        "media_extensions_csv",
        "exclude_markers_csv",
        "include_patterns_csv",
        "exclude_patterns_csv",
        "min_file_size_mb",
        "max_file_size_mb",
        "min_file_age_seconds",
        "exclude_hidden",
        "top_level_only",
        "scan_interval_seconds",
        "hold_minutes",
        "sidecar_patterns_csv",
        "preserve_original_timestamps",
        "output_collision_policy",
        "file_detection_interval_seconds",
        "ignore_size_changes",
        "skip_access_tests",
        "file_system_events_enabled",
        "max_attempts",
        "retry_backoff_seconds",
        "retry_execution_failures",
        "retry_preflight_failures",
        "schedule_enabled",
        "schedule_hours_limited",
        "schedule_days",
        "schedule_start",
        "schedule_end",
        "max_concurrent_files",
        "priority",
    ):
        setattr(row, field, getattr(body, field))
    # Validated rather than stored as given: a grid of the wrong length would switch work
    # on or off at times nobody chose, and failing the save is the honest outcome.
    grid = getattr(body, "schedule_grid", "")
    try:
        row.schedule_grid = normalize_grid(grid)
    except ScheduleGridError as exc:
        raise RefinerLibraryError(str(exc)) from exc
    row.rule_set_id = _validate_rule_set(session, getattr(body, "rule_set_id", None))


def _set_manager_links(session: Session, row: RefinerLibraryRow, connection_ids: list[int]) -> None:
    wanted = _validate_manager_connections(session, connection_ids)
    existing = set(manager_connection_ids_for(session, row))
    for stale in existing - set(wanted):
        link = session.scalars(
            select(RefinerLibraryManagerLinkRow)
            .where(RefinerLibraryManagerLinkRow.library_id == row.id)
            .where(RefinerLibraryManagerLinkRow.connection_id == stale)
        ).first()
        if link is not None:
            session.delete(link)
    for added in set(wanted) - existing:
        session.add(RefinerLibraryManagerLinkRow(library_id=row.id, connection_id=added))
    session.flush()


def create_library(session: Session, body: object) -> RefinerLibraryRow:
    name = _validate_name(session, body.name)  # type: ignore[attr-defined]
    scope = _validate_scope(body.media_scope)  # type: ignore[attr-defined]
    highest = session.scalars(
        select(RefinerLibraryRow.display_order).order_by(RefinerLibraryRow.display_order.desc())
    ).first()
    row = RefinerLibraryRow(name=name, media_scope=scope, display_order=(highest or 0) + 1)
    _apply_fields(session, row, body)
    session.add(row)
    session.flush()
    _set_manager_links(session, row, list(body.manager_connection_ids))  # type: ignore[attr-defined]
    return row


def update_library(session: Session, row: RefinerLibraryRow, body: object) -> RefinerLibraryRow:
    row.name = _validate_name(session, body.name, exclude_id=row.id)  # type: ignore[attr-defined]
    row.media_scope = _validate_scope(body.media_scope)  # type: ignore[attr-defined]
    _apply_fields(session, row, body)
    session.add(row)
    session.flush()
    _set_manager_links(session, row, list(body.manager_connection_ids))  # type: ignore[attr-defined]
    return row


def delete_library(session: Session, row: RefinerLibraryRow) -> None:
    """Refuse while work is in flight; those jobs resolve their paths from this library."""

    active = active_job_count_for_library(session, row)
    if active:
        raise RefinerLibraryError(
            f"{row.name} still has {active} job{'' if active == 1 else 's'} queued or running. "
            "Wait for them to finish, or cancel them, before removing the library — they resolve their "
            "folders from it."
        )
    session.delete(row)
    session.flush()


def reorder_libraries(session: Session, library_ids_in_order: list[int]) -> list[RefinerLibraryRow]:
    rows = {row.id: row for row in list_libraries(session)}
    unknown = [i for i in library_ids_in_order if i not in rows]
    if unknown:
        raise RefinerLibraryError(f"No library with id {unknown[0]}.")
    if len(set(library_ids_in_order)) != len(rows):
        raise RefinerLibraryError("Reordering must list every library exactly once.")
    for position, library_id in enumerate(library_ids_in_order):
        rows[library_id].display_order = position
    session.flush()
    return list_libraries(session)


def rule_set_usage_count(session: Session, rule_set: RefinerRuleSetRow) -> int:
    return len(list(session.scalars(select(RefinerLibraryRow.id).where(RefinerLibraryRow.rule_set_id == rule_set.id))))


def create_rule_set(session: Session, body: object) -> RefinerRuleSetRow:
    label = (body.name or "").strip()  # type: ignore[attr-defined]
    if session.scalars(select(RefinerRuleSetRow).where(RefinerRuleSetRow.name == label)).first():
        raise RefinerLibraryError(f"A rule set named {label!r} already exists.")
    row = RefinerRuleSetRow(name=label)
    _apply_rule_set_fields(row, body)
    session.add(row)
    session.flush()
    return row


def update_rule_set(session: Session, row: RefinerRuleSetRow, body: object) -> RefinerRuleSetRow:
    label = (body.name or "").strip()  # type: ignore[attr-defined]
    clash = session.scalars(select(RefinerRuleSetRow).where(RefinerRuleSetRow.name == label)).first()
    if clash is not None and clash.id != row.id:
        raise RefinerLibraryError(f"A rule set named {label!r} already exists.")
    row.name = label
    _apply_rule_set_fields(row, body)
    session.add(row)
    session.flush()
    return row


def _apply_rule_set_fields(row: RefinerRuleSetRow, body: object) -> None:
    for field in (
        "primary_audio_lang",
        "secondary_audio_lang",
        "tertiary_audio_lang",
        "default_audio_slot",
        "remove_commentary",
        "subtitle_mode",
        "subtitle_langs_csv",
        "preserve_forced_subs",
        "preserve_default_subs",
        "audio_preference_mode",
        "remove_images",
        "remove_attachments",
        "remove_title",
        "remove_language_tags",
        "remove_other_metadata",
    ):
        setattr(row, field, getattr(body, field))
    _apply_sorter_fields(row, body)


def _apply_sorter_fields(row: RefinerRuleSetRow, body: object) -> None:
    """Validate and store the two sorter lists.

    Validated rather than stored as given: a list quietly missing the field an operator
    typed would change how their files are ranked without telling them.
    """

    for field in ("audio_sorters_json", "subtitle_sorters_json"):
        raw = getattr(body, field, None)
        if raw is None:
            continue
        try:
            setattr(row, field, validate_sorters(raw))
        except TrackSorterError as exc:
            raise RefinerLibraryError(str(exc)) from exc

    # An empty audio list is filled from the chosen policy's preset. That is what makes
    # the three policies *presets* rather than a separate mechanism: an operator picks
    # one, sees the sorters it stands for, and can then edit them — which was the whole
    # point, because previously the policy was all they could change.
    if not (row.audio_sorters_json or "").strip():
        row.audio_sorters_json = dump_sorters(preset_sorters(getattr(body, "audio_preference_mode", None)))


def delete_rule_set(session: Session, row: RefinerRuleSetRow) -> None:
    used = rule_set_usage_count(session, row)
    if used:
        raise RefinerLibraryError(
            f"{row.name} is still used by {used} librar{'y' if used == 1 else 'ies'}. "
            "Point them at another rule set first — removing it would strip their audio and subtitle handling."
        )
    session.delete(row)
    session.flush()
