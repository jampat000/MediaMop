"""Reject a release Weir could not process, so the manager can find a different one (#465, #471).

``reject`` is the opt-in third failure policy. ``pass_through`` hands the original back; ``hold``
keeps it; ``reject`` tells the manager the release is bad and has the download removed, so the
manager can blocklist it and fetch another.

Deleting someone's download is irreversible, so the rules here are strict and each is easy to
"simplify" wrongly:

**Report first, remove second.** Nothing is removed until the manager has accepted the report
(a 2xx answer). "Could not reach it" and "it refused" are treated the same: not accepted.

**Anything short of certainty falls back to pass-through.** Never to deleting a file nobody was
told about, and never to silently doing nothing. The fallback is recorded in Activity with the
reason.

**Each kind of manager is asked through its port, the way it documents** (ADR-0015; the product
specifics live in ``platform/media_managers/manager_dialects.py``):

- *A manager that hands files over* gets a ``failed`` hand-off report with
  ``disposition: rejected`` — but only when its manifest advertises ``processor-reject-regrab``
  (Deluno#497). Until a manager can fetch a replacement, rejecting would delete a download with
  nothing coming to replace it. Weir removes the source itself once the report is accepted.
- *A manager whose port removes queue items* is asked to remove the matching item and blocklist
  its release; its download client removes the data, so Weir deletes nothing itself. This acts
  only when **exactly one** queue item matches **and** that download holds only this one video
  file: removing a season pack's queue item would delete every episode in it.

**It runs as its own durable job**, like pass-through, so no HTTP call or delete ever happens
inside a database transaction.

**Reports are paced.** A library full of unprocessable files must not fire a burst of calls at
a manager, so reject jobs are spaced out process-wide.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from weir.core.config import WeirSettings
from weir.platform.activity import constants as activity_constants
from weir.platform.activity import service as activity_service
from weir.platform.media_managers.completion_callback import (
    HandoffOrigin,
    HandoffReportDelivery,
    HandoffReportTarget,
    build_completion_body,
    post_handoff_report,
    record_handoff_report,
    resolve_handoff_target,
)
from weir.platform.media_managers.handoff_ledger import STATE_REJECTED, record_handoff_outcome
from weir.platform.media_managers.manager_binding import connections_by_id
from weir.platform.media_managers.manager_dialects import port_for_kind
from weir.platform.media_managers.manager_http import MediaManagerHttpError
from weir.platform.media_managers.manager_port import ManagerConnection
from weir.refiner.queue_row_plumbing import first_str, normalize_storage_path, output_path
from weir.refiner.refiner_file_state_model import RefinerFileStatus
from weir.refiner.refiner_file_state_service import mark_file_status
from weir.refiner.refiner_library_service import manager_connection_ids_for, resolve_library
from weir.refiner.refiner_pass_through import enqueue_pass_through
from weir.refiner.refiner_rejected_file_cleanup import cleanup_rejected_file
from weir.refiner.refiner_remux_rules import REFINER_MEDIA_EXTENSIONS

logger = logging.getLogger(__name__)

#: What a manager's manifest must advertise before Weir will reject through a hand-off.
REJECT_CAPABILITY = "processor-reject-regrab"

#: Minimum spacing between outbound rejects, across the whole process.
MIN_SECONDS_BETWEEN_REJECTS = 2.0


def _removes_queue_items(kind: str) -> bool:
    port = port_for_kind(kind)
    return port is not None and port.capabilities().removes_queue_items


_pace_lock = threading.Lock()
_last_reject_at = 0.0


@dataclass(frozen=True, slots=True)
class RejectSupport:
    """Whether a library's managers can take a rejection, and the sentence that explains it."""

    available: bool
    reason: str


def reject_support(connections: Sequence[ManagerConnection]) -> RejectSupport:
    """Whether ``reject`` can be offered for a library linked to ``connections``.

    A manager whose port removes queue items can always be asked (the safety rules are applied per
    file at run time). Any other manager must advertise the capability, so it is asked for its manifest.
    """

    if not connections:
        return RejectSupport(
            False,
            "Link a media manager to this library first. Rejecting needs a manager that can find a different release.",
        )
    reasons: list[str] = []
    for connection in connections:
        port = port_for_kind(connection.kind)
        if port is None:
            continue
        if port.capabilities().removes_queue_items:
            return RejectSupport(
                True,
                f"{connection.label} can remove the download, blocklist the release and search for another. "
                "Weir only does this when the download holds just this one file; otherwise it hands the "
                "original back.",
            )
        description = port.describe(connection)
        if description.status != "reported":
            reasons.append(description.detail or f"Weir could not ask {connection.label} what it can do.")
            continue
        if REJECT_CAPABILITY in description.advertised_capabilities:
            return RejectSupport(
                True,
                f"{connection.label} says it can blocklist a bad release and find another. Weir removes "
                "the download only after it accepts the report.",
            )
        reasons.append(
            f"{connection.label} does not yet say it can replace a rejected release, so rejecting would "
            "delete a download with nothing coming to replace it."
        )
    if not reasons:
        reasons.append("None of the linked media managers can take a rejection.")
    return RejectSupport(False, " ".join(reasons))


def _pace() -> None:
    global _last_reject_at
    with _pace_lock:
        wait = MIN_SECONDS_BETWEEN_REJECTS - (time.monotonic() - _last_reject_at)
        if wait > 0:
            time.sleep(wait)
        _last_reject_at = time.monotonic()


@dataclass(slots=True)
class RejectAttempt:
    """What happened. ``done`` means the manager accepted; otherwise ``reason`` says why not."""

    done: bool
    reason: str
    manager: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    report: tuple[HandoffReportTarget, dict[str, Any], HandoffReportDelivery] | None = None


def _reject_through_handoff(
    *,
    target: HandoffReportTarget,
    origin: HandoffOrigin,
    source: Path,
    watched_root: Path,
    reason: str,
    failure_class: str | None,
) -> RejectAttempt:
    connection = target.connection
    label = connection.label
    port = port_for_kind(connection.kind)
    if port is None:
        return RejectAttempt(False, f"Weir does not know how to ask {label} what it can do.", manager=label)
    description = port.describe(connection)
    if description.status != "reported":
        return RejectAttempt(False, description.detail or f"Weir could not ask {label} what it can do.", manager=label)
    if REJECT_CAPABILITY not in description.advertised_capabilities:
        return RejectAttempt(
            False,
            f"{label} does not yet say it can replace a rejected release, so Weir did not delete the download.",
            manager=label,
        )
    if not source.is_file():
        return RejectAttempt(False, f"The original is no longer at {source}, so there is nothing to reject.")

    result: dict[str, Any] = {"ok": False, "outcome": "failed", "reason": reason}
    if failure_class:
        result["failure_class"] = failure_class
    body = build_completion_body(origin=origin, result=result, rejected=True)
    delivery = post_handoff_report(target, body)
    report = (target, body, delivery)
    if not delivery.accepted:
        return RejectAttempt(
            False,
            f"{label} did not accept the rejection ({delivery.status.removeprefix('failed: ')}), so Weir kept "
            "the download.",
            manager=label,
            report=report,
        )
    cleanup = cleanup_rejected_file(watched_root=watched_root, file_path=source, action="delete_file")
    sentence = f"{label} accepted that this release is bad and can find a different one. {cleanup.detail}"
    if not cleanup.deleted:
        sentence = (
            f"{label} accepted that this release is bad, but Weir could not remove the download: "
            f"{cleanup.detail} Remove it by hand; Weir will not process it again."
        )
    return RejectAttempt(
        True,
        sentence,
        manager=label,
        detail={"route": "handoff", "source_removed": cleanup.deleted},
        report=report,
    )


def _single_video_file_under(folder: Path) -> Path | None:
    """The only video file in a download folder, or None when there is not exactly one."""

    try:
        found = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in REFINER_MEDIA_EXTENSIONS]
    except OSError:
        return None
    return found[0].resolve() if len(found) == 1 else None


def _reject_through_queue(*, connections: Sequence[ManagerConnection], source: Path) -> RejectAttempt:
    matches: list[tuple[ManagerConnection, dict[str, Any], bool]] = []
    rows_by_connection: dict[int, list[dict[str, Any]]] = {}
    wanted = normalize_storage_path(str(source))
    for index, connection in enumerate(connections):
        port = port_for_kind(connection.kind)
        if port is None:
            continue
        signal = port.queue_rows(connection)
        if not signal.is_reported:
            # Without every linked manager's answer, "exactly one match" cannot be known.
            return RejectAttempt(
                False,
                signal.detail or f"Weir could not read {connection.label}'s queue.",
                manager=connection.label,
            )
        rows = [dict(row.payload) for row in signal.rows]
        rows_by_connection[index] = rows
        for row in rows:
            out = output_path(row)
            if out is None:
                continue
            folder = normalize_storage_path(out).rstrip("/")
            if folder == wanted:
                matches.append((connection, row, False))
            elif folder and wanted.startswith(f"{folder}/"):
                matches.append((connection, row, True))

    if not matches:
        return RejectAttempt(
            False,
            "No download in the linked media manager's queue points at this file, so Weir could not reject it safely.",
        )
    if len(matches) > 1:
        return RejectAttempt(
            False,
            "More than one download in the queue points at this file, so Weir could not tell which one to reject.",
        )

    connection, row, is_folder = matches[0]
    label = connection.label
    download_id = first_str(row, "downloadId")
    index = connections.index(connection)
    if download_id is not None:
        siblings = [r for r in rows_by_connection.get(index, []) if first_str(r, "downloadId") == download_id]
        if len(siblings) > 1:
            return RejectAttempt(
                False,
                f"This file is part of a download that {label} tracks as {len(siblings)} items (a season pack or "
                "similar). Rejecting it would delete the others too, so Weir handed the original back instead.",
                manager=label,
            )
    if is_folder:
        download_folder = Path(output_path(row) or "")
        only = _single_video_file_under(download_folder)
        if only is None or only != source.resolve():
            return RejectAttempt(
                False,
                f"The download holds more than this one video file. Rejecting it in {label} would delete the "
                "others too, so Weir handed the original back instead.",
                manager=label,
            )

    port = port_for_kind(connection.kind)
    if port is None:
        return RejectAttempt(False, f"Weir does not know how to ask {label} to remove a download.", manager=label)
    try:
        port.remove_queue_item(connection, row)
    except (MediaManagerHttpError, OSError) as exc:
        return RejectAttempt(
            False,
            f"{label} did not accept the rejection, so nothing was removed.",
            manager=label,
            detail={"technical_detail": str(exc)[:500]},
        )
    return RejectAttempt(
        True,
        f"{label} removed the download and blocklisted the release, so it will not be grabbed again and "
        f"{label} can search for a different one.",
        manager=label,
        detail={"route": "queue", "queue_item": row.get("id"), "download_id": download_id},
    )


def make_refiner_file_reject_handler(
    settings: WeirSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[Any], None]:
    """Worker handler for ``refiner.file.reject.v1``."""

    def _run(ctx: Any) -> None:
        try:
            payload = json.loads(ctx.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        relative_path = str(payload.get("relative_media_path") or "").strip()
        library_id = payload.get("library_id") if isinstance(payload.get("library_id"), int) else None
        if not relative_path or library_id is None:
            msg = "A reject job needs a file and a library."
            raise ValueError(msg)
        origin_raw = payload.get("origin") if isinstance(payload.get("origin"), dict) else None
        reason = str(payload.get("reason") or "Weir could not process this file.")
        failure_class = payload.get("failure_class") if isinstance(payload.get("failure_class"), str) else None

        # 1. Everything the attempt needs, read with the session closed before any network call.
        with session_factory() as session:
            library = resolve_library(session, library_id=library_id)
            if library is None:
                msg = f"Library {library_id} no longer exists."
                raise RuntimeError(msg)
            watched_root = Path(str(library.watched_folder)).resolve()
            origin = HandoffOrigin.from_payload({"origin": origin_raw}) if origin_raw else None
            target: HandoffReportTarget | str | None = None
            if (
                origin is not None
                and port_for_kind(origin.source_key) is not None
                and not _removes_queue_items(origin.source_key)
            ):
                target = resolve_handoff_target(session, settings, origin)
            queue_connections = [
                c
                for c in connections_by_id(session, settings, manager_connection_ids_for(session, library))
                if _removes_queue_items(c.kind)
            ]
        source = (watched_root / relative_path).resolve()

        # 2. The attempt, paced, with no transaction open.
        _pace()
        if origin is not None and target is not None:
            if isinstance(target, str):
                attempt = RejectAttempt(False, f"Weir could not report to the manager: {target}.")
            else:
                attempt = _reject_through_handoff(
                    target=target,
                    origin=origin,
                    source=source,
                    watched_root=watched_root,
                    reason=reason,
                    failure_class=failure_class,
                )
        elif queue_connections:
            attempt = _reject_through_queue(connections=queue_connections, source=source)
        else:
            attempt = RejectAttempt(
                False,
                "No linked media manager can take a rejection for this file, so Weir handed the original back instead.",
            )

        # 3. Bookkeeping, and the fallback, in one short transaction.
        with session_factory() as session, session.begin():
            if attempt.report is not None:
                report_target, body, delivery = attempt.report
                record_handoff_report(
                    session, target=report_target, body=body, delivery=delivery, relative_path=relative_path
                )
            detail: dict[str, Any] = {
                "job_id": ctx.id,
                "relative_media_path": relative_path,
                "library_id": library_id,
                "manager": attempt.manager,
                "message": attempt.reason,
                "trigger": "worker",
                # Falling back is recoverable and the file still reaches the manager: a warning, not a failure.
                "result": "success" if attempt.done else "warning",
                **attempt.detail,
            }
            if attempt.done:
                mark_file_status(
                    session,
                    library_id=library_id,
                    relative_path=relative_path,
                    status=RefinerFileStatus.REJECTED,
                    reason=attempt.reason,
                )
                if origin is not None:
                    record_handoff_outcome(
                        session,
                        source_key=origin.source_key,
                        handoff_id=origin.handoff_id,
                        state=STATE_REJECTED,
                        message=attempt.reason,
                    )
                event_type = activity_constants.REFINER_FILE_REJECTED
                title = f"{Path(relative_path).name} was rejected so a different release can be found"
            else:
                live_library = resolve_library(session, library_id=library_id)
                if live_library is not None:
                    enqueue_pass_through(session, library=live_library, relative_path=relative_path, origin=origin_raw)
                mark_file_status(
                    session,
                    library_id=library_id,
                    relative_path=relative_path,
                    status=RefinerFileStatus.PROCESSING_FAILED,
                    reason=f"{reason} {attempt.reason} Weir is handing the original back unchanged instead."[:10_000],
                )
                event_type = activity_constants.REFINER_FILE_REJECT_FELL_BACK
                title = f"{Path(relative_path).name} could not be rejected, so it is being handed back"
                detail["next_action"] = "Weir queued the original to be handed back unchanged."
            activity_service.record_activity_event(
                session,
                event_type=event_type,
                module="refiner",
                title=title,
                detail=json.dumps(detail, separators=(",", ":"), ensure_ascii=True)[:10_000],
            )
        logger.info("Refiner reject for %s: %s", relative_path, attempt.reason)

    return _run
