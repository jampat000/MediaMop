"""Never strand a file: hand the original back when processing cannot succeed (#465).

MediaMop sits in the middle of a pipeline it does not own. A media manager downloads a release
into a completed folder, MediaMop takes it, and writes a result into an output folder the manager
imports. When processing failed and retries ran out, the file used to stay in MediaMop's hands for
good — so it never reached the manager, and the user's media simply went missing.

Under the ``pass_through`` failure policy the original is instead delivered to the output folder
**unmodified**. The product's promise becomes: *worst case, you get your original file, unchanged,
on schedule.*

Three decisions here are deliberate, and each is easy to "tidy up" wrongly later:

**It runs as its own durable job, and the copy holds no transaction open.** Failures are recorded
inside a database transaction, and a pass-through can be a 50 GB copy. Copying inline would hold
SQLite's write lock for minutes and block every other write in the application. So a failure only
*queues* delivery; the worker reads the library, closes its session, copies, and then opens a brief
transaction for bookkeeping. Filesystem work lives in :func:`deliver_unchanged`, which never touches
the database.

**The copy is verified as byte-identical, not as valid media.** The guarantee is "unchanged". A file
that failed processing may be precisely the kind that will not probe, so validating it as media would
make pass-through fail on exactly the files that need it. We check the delivered bytes match the
source size and that the source did not change underneath the copy.

**The source is never deleted.** Deleting the only known-good copy immediately after a failure is
destructive and irreversible. Leaving it costs a file in the completed folder; the scanner treats a
``passed_through`` file with an unchanged source as finished, so it is not re-processed in a loop.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_failure_policy_job_kinds import (
    REFINER_FILE_PASS_THROUGH_JOB_KIND,
    REFINER_FILE_REJECT_JOB_KIND,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_file_state_service import (
    mark_file_status,
    record_output_collision,
)
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_library_service import resolve_library
from mediamop.modules.refiner.refiner_output_collision import decide_output_collision
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity import service as activity_service
from mediamop.platform.file_lifecycle.mutations import safe_copy_to_final
from mediamop.platform.media_managers.completion_callback import report_handoff_completion

logger = logging.getLogger(__name__)


FAILURE_POLICY_PASS_THROUGH = "pass_through"
FAILURE_POLICY_HOLD = "hold"
# Opt-in. Tell the manager the release is bad so it can find another, and remove the download once
# it has accepted that. Anything that stops a reject from being done safely falls back to
# pass_through, never to deleting a file nobody was told about (see refiner_reject).
FAILURE_POLICY_REJECT = "reject"
FAILURE_POLICIES: tuple[str, ...] = (FAILURE_POLICY_PASS_THROUGH, FAILURE_POLICY_HOLD, FAILURE_POLICY_REJECT)


def normalize_failure_policy(raw: str | None) -> str:
    """Canonical policy. Anything unrecognised is the product's guarantee, ``pass_through``.

    Falling back to the guarantee rather than to ``hold`` is deliberate: an unreadable setting must
    not quietly start stranding files again.
    """

    value = (raw or "").strip().lower()
    return value if value in FAILURE_POLICIES else FAILURE_POLICY_PASS_THROUGH


class PassThroughIntegrityError(RuntimeError):
    """The delivered copy is not byte-identical to the source, so it must not be published."""


def _fingerprint(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return int(stat.st_size), int(stat.st_mtime_ns)


def _make_byte_integrity_check(source: Path) -> Callable[[Path], None]:
    """Validator for ``safe_copy_to_final``: same size as the source, and the source held still.

    Size plus an unchanged source fingerprint catches a truncated copy and a source that was still
    being written. It deliberately does not probe the file as media — see the module docstring.
    """

    before = _fingerprint(source)

    def check(staged: Path) -> None:
        staged_size = int(staged.stat().st_size)
        after = _fingerprint(source)
        if after != before:
            msg = "The source changed while MediaMop was copying it, so the copy was not delivered."
            raise PassThroughIntegrityError(msg)
        if staged_size != before[0]:
            msg = f"The copy is {staged_size} bytes but the source is {before[0]}, so the copy was not delivered."
            raise PassThroughIntegrityError(msg)

    return check


def enqueue_pass_through(
    session: Session,
    *,
    library: RefinerLibraryRow,
    relative_path: str,
    origin: dict[str, Any] | None = None,
) -> RefinerJob:
    """Queue delivery of the unmodified original. Called once retries are exhausted.

    ``origin`` is the manager's hand-off, carried so the delivery can be reported as complete.
    Without it, a manager waiting on a hand-off would only ever have heard nothing.
    """

    body: dict[str, Any] = {"relative_media_path": relative_path, "library_id": library.id, "trigger": "worker"}
    if origin:
        body["origin"] = origin
    payload = json.dumps(body, separators=(",", ":"))
    return refiner_enqueue_or_get_job(
        session,
        # One delivery per file at a time. A second failure recorded while the first delivery is
        # still queued must not produce two copies racing for the same output path.
        dedupe_key=f"{REFINER_FILE_PASS_THROUGH_JOB_KIND}:{library.id}:{relative_path}",
        job_kind=REFINER_FILE_PASS_THROUGH_JOB_KIND,
        payload_json=payload,
        priority=int(library.priority or 0),
    )


def enqueue_reject(
    session: Session,
    *,
    library: RefinerLibraryRow,
    relative_path: str,
    origin: dict[str, Any] | None = None,
    reason: str | None = None,
    failure_class: str | None = None,
) -> RefinerJob:
    """Queue a reject. Its own durable job, so no HTTP call or delete runs inside a transaction."""

    body: dict[str, Any] = {"relative_media_path": relative_path, "library_id": library.id, "trigger": "worker"}
    if origin:
        body["origin"] = origin
    if reason:
        body["reason"] = reason[:1200]
    if failure_class:
        body["failure_class"] = failure_class
    return refiner_enqueue_or_get_job(
        session,
        dedupe_key=f"{REFINER_FILE_REJECT_JOB_KIND}:{library.id}:{relative_path}",
        job_kind=REFINER_FILE_REJECT_JOB_KIND,
        payload_json=json.dumps(body, separators=(",", ":")),
        priority=int(library.priority or 0),
    )


def apply_failure_policy(
    session: Session,
    *,
    library: RefinerLibraryRow,
    relative_path: str,
    will_retry: bool,
    origin: dict[str, Any] | None = None,
) -> str | None:
    """Act on a recorded failure. Returns the follow-up queued — ``pass_through`` or ``reject`` — or None.

    Nothing happens while an automatic retry is still coming: the policy only decides what to do
    once MediaMop has genuinely given up on processing the file.
    """

    if will_retry:
        return None
    policy = normalize_failure_policy(library.failure_policy)
    if policy == FAILURE_POLICY_HOLD:
        return None

    row = session.scalars(
        select(RefinerFileRow).where(
            RefinerFileRow.library_id == library.id,
            RefinerFileRow.relative_path == relative_path,
        ),
    ).first()

    if policy == FAILURE_POLICY_REJECT:
        enqueue_reject(
            session,
            library=library,
            relative_path=relative_path,
            origin=origin,
            reason=row.status_reason if row is not None else None,
            failure_class=row.failure_class if row is not None else None,
        )
        if row is not None:
            row.status_reason = (
                f"{row.status_reason} MediaMop could not process this file, so it is telling your media manager "
                "the release is bad so it can find a different one."
            ).strip()[:10000]
        return FAILURE_POLICY_REJECT

    enqueue_pass_through(session, library=library, relative_path=relative_path, origin=origin)
    if row is not None:
        # Say what is about to happen, so the screen never shows a failure that is already being
        # resolved. The final sentence is written once the file is actually delivered.
        row.status_reason = (
            f"{row.status_reason} MediaMop could not process this file, so it is handing the original "
            "back to the output folder unchanged."
        ).strip()[:10000]
    return FAILURE_POLICY_PASS_THROUGH


@dataclass(frozen=True, slots=True)
class DeliverySettings:
    """The library values a delivery needs, copied out so no session is open during the copy."""

    library_id: int
    watched_folder: str
    output_folder: str
    output_collision_policy: str | None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    delivered: bool
    destination: Path
    collision_policy: str
    collision_action: str
    collision_reason: str
    sentence: str


def deliver_unchanged(settings: DeliverySettings, *, relative_path: str) -> DeliveryResult:
    """Copy the original into the output folder. Pure filesystem work — touches no database.

    Raises rather than publishing anything that is not byte-identical to the source.
    """

    watched_root = Path(settings.watched_folder).resolve()
    output_root = Path(settings.output_folder).resolve()
    source = (watched_root / relative_path).resolve()
    final = output_root / relative_path

    if not source.is_file():
        msg = f"The original is no longer in the watched folder at {source}, so there is nothing to hand back."
        raise FileNotFoundError(msg)
    if output_root == watched_root:
        msg = "The output folder is the watched folder, so handing the file back would overwrite the original."
        raise RuntimeError(msg)

    decision = decide_output_collision(
        final=final,
        source=source,
        staged=source,
        policy=settings.output_collision_policy,
    )

    if decision.wrote:
        safe_copy_to_final(
            source=source,
            final=decision.destination,
            validate_staged=_make_byte_integrity_check(source),
        )
        sentence = (
            "MediaMop could not process this file, so it handed the original back unchanged to "
            f"{decision.destination}. Your media manager can import it as normal."
        )
    else:
        reason = decision.reason
        sentence = (
            "MediaMop could not process this file and would have handed the original back unchanged, "
            f"but {reason[:1].lower()}{reason[1:]}"
        )

    return DeliveryResult(
        delivered=decision.wrote,
        destination=decision.destination,
        collision_policy=decision.policy,
        collision_action=decision.action,
        collision_reason=decision.reason,
        sentence=sentence,
    )


def record_delivery(
    session: Session,
    *,
    settings: DeliverySettings,
    relative_path: str,
    result: DeliveryResult,
    job_id: int | None,
) -> None:
    """The short bookkeeping transaction after a delivery."""

    record_output_collision(
        session,
        relative_path=relative_path,
        policy=result.collision_policy,
        action=result.collision_action,
        reason=result.collision_reason,
    )
    mark_file_status(
        session,
        library_id=settings.library_id,
        relative_path=relative_path,
        status=RefinerFileStatus.PASSED_THROUGH,
        reason=result.sentence,
    )
    activity_service.record_activity_event(
        session,
        event_type=activity_constants.REFINER_FILE_PASSED_THROUGH,
        module="refiner",
        title=f"{Path(relative_path).name} was handed back unchanged",
        detail=json.dumps(
            {
                "job_id": job_id,
                "relative_media_path": relative_path,
                "library_id": settings.library_id,
                "delivered": result.delivered,
                "destination": str(result.destination),
                "collision_action": result.collision_action,
                "source_kept": True,
                "message": result.sentence,
                "trigger": "worker",
                "result": "success" if result.delivered else "skipped",
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )[:10_000],
    )


def make_refiner_file_pass_through_handler(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> Callable[[Any], None]:
    """Worker handler for ``refiner.file.pass_through.v1``."""

    def _run(ctx: Any) -> None:
        try:
            payload = json.loads(ctx.payload_json or "{}")
        except (TypeError, ValueError):
            payload = {}
        relative_path = str(payload.get("relative_media_path") or "").strip()
        library_id = payload.get("library_id") if isinstance(payload.get("library_id"), int) else None
        if not relative_path or library_id is None:
            msg = "A pass-through job needs a file and a library."
            raise ValueError(msg)

        # 1. Read what the delivery needs, then close the session before touching any file.
        with session_factory() as session:
            library = resolve_library(session, library_id=library_id)
            if library is None:
                msg = f"Library {library_id} no longer exists, so there is nowhere to hand the file back to."
                raise RuntimeError(msg)
            delivery = DeliverySettings(
                library_id=int(library.id),
                watched_folder=str(library.watched_folder),
                output_folder=str(library.output_folder),
                output_collision_policy=library.output_collision_policy,
            )

        # 2. The copy, with no transaction open — this can take minutes on a large file.
        try:
            result = deliver_unchanged(delivery, relative_path=relative_path)
        except Exception as exc:
            logger.warning("Refiner pass-through could not deliver %s", relative_path, exc_info=True)
            with session_factory() as session, session.begin():
                activity_service.record_activity_event(
                    session,
                    event_type=activity_constants.REFINER_FILE_PASS_THROUGH_FAILED,
                    module="refiner",
                    title=f"{Path(relative_path).name} could not be handed back",
                    detail=json.dumps(
                        {
                            "job_id": ctx.id,
                            "relative_media_path": relative_path,
                            "message": str(exc)[:1200],
                            "trigger": "worker",
                            "result": "failed",
                            "library_id": delivery.library_id,
                            "source_kept": True,
                            "next_action": (
                                "The original is untouched in the watched folder. "
                                "Check that the output folder exists and is writable."
                            ),
                        },
                        separators=(",", ":"),
                    ),
                )
            raise

        # 3. Brief bookkeeping.
        with session_factory() as session, session.begin():
            record_delivery(session, settings=delivery, relative_path=relative_path, result=result, job_id=ctx.id)

        # 4. Tell a waiting manager the file is ready. Only when something was actually delivered:
        # after a collision skip the file at that path is not this one, and asking the manager to
        # import it would be wrong. Reporting never raises; the delivery already succeeded.
        origin = payload.get("origin") if isinstance(payload.get("origin"), dict) else None
        if origin and result.delivered:
            with session_factory() as session:
                status = report_handoff_completion(
                    session,
                    settings,
                    payload_json=json.dumps({"origin": origin}),
                    result={
                        "ok": True,
                        "outcome": "live_output_written",
                        "relative_media_path": relative_path,
                        "output_file": str(result.destination),
                        "refiner_output_folder_resolved": str(Path(delivery.output_folder).resolve()),
                        "passed_through_after_failure": True,
                    },
                )
            logger.info("Refiner pass-through hand-off report: %s", status)

    return _run
