"""Refiner HTTP: "why is this file held?" — ``/api/v1/refiner/files/{id}/why-held``.

This was a queued job family (``refiner.candidate_gate.v1``) with no scheduler and no UI
calling it: an operator asked a question and got a job id back, then had to go and find
the answer in the activity feed. It is a **read-only question with an answer the caller
wants immediately**, so it is a synchronous endpoint now and the queue round-trip is gone.

The rules are unchanged — the same evaluator the watched-folder scan applies per file,
asked about one file on demand. Its reasons were already written for operators, so they
are returned exactly as they are rather than being re-worded here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path
from starlette import status as http_status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.modules.refiner.refiner_candidate_gate_evaluate import (
    evaluate_refiner_candidate_gate_from_manager_signals,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_library_service import manager_connection_ids_for
from mediamop.modules.refiner.schemas_refiner_hold_diagnostic import RefinerWhyHeldOut
from mediamop.platform.auth.deps_auth import UserPublicDep
from mediamop.platform.media_managers.manager_binding import collect_queue_signals
from mediamop.platform.media_managers.manager_port import MediaScope

router = APIRouter(tags=["refiner"])


def _release_title_from_relative_path(relative_path: str) -> str:
    """The title to anchor against, taken from the path the scan recorded.

    The folder name is a better anchor than the file name for a release directory, and
    the file stem is the only thing available when a file sits at the root.
    """

    parts = [segment for segment in relative_path.replace("\\", "/").split("/") if segment]
    if len(parts) >= 2:
        return parts[-2]
    if parts:
        stem = parts[-1]
        return stem.rsplit(".", 1)[0] if "." in stem else stem
    return relative_path


@router.get("/refiner/files/{file_id}/why-held", response_model=RefinerWhyHeldOut)
def get_refiner_file_why_held(
    _user: UserPublicDep,
    db: DbSessionDep,
    settings: SettingsDep,
    file_id: int = Path(ge=1),
) -> RefinerWhyHeldOut:
    """Ask every manager covering this file's library what it is doing with it, right now.

    Deliberately live rather than cached: the question is only ever asked because the
    recorded state looks wrong or stale, and answering it from the same record would be
    no answer at all.
    """

    row = db.get(RefinerFileRow, file_id)
    if row is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="MediaMop has no record of that file.")
    library = db.get(RefinerLibraryRow, row.library_id)
    if library is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="The library this file belonged to no longer exists.",
        )

    media_scope: MediaScope = "tv" if library.media_scope == "tv" else "movie"
    connection_ids = list(manager_connection_ids_for(db, library))
    signals = collect_queue_signals(
        db,
        settings,
        media_scope=media_scope,
        connection_ids=connection_ids or None,
    )
    outcome = evaluate_refiner_candidate_gate_from_manager_signals(
        media_scope=media_scope,
        signals=signals,
        release_title=_release_title_from_relative_path(row.relative_path),
        release_year=None,
        output_path=row.relative_path,
        entity_id=None,
    )
    return RefinerWhyHeldOut(
        file_id=file_id,
        relative_path=row.relative_path,
        library_name=library.name,
        recorded_status=row.status,
        recorded_reason=row.status_reason,
        verdict=outcome.verdict,
        owned=outcome.owned,
        blocked_upstream=outcome.blocked_upstream,
        blocked_by_connection=outcome.blocked_by_connection,
        queue_row_count=outcome.queue_row_count,
        managers_consulted=outcome.managers_consulted,
        managers_reporting=outcome.managers_reporting,
        managers_without_queue_signal=list(outcome.managers_without_queue_signal),
        reasons=list(outcome.reasons),
    )
