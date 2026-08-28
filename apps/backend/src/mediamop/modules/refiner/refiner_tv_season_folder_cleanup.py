"""TV-only post-success watched-folder season cleanup (Refiner ``media_scope=tv``).

Movies release-folder cleanup lives only in :mod:`refiner_file_remux_pass_run`; do not merge code paths.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.domain import FileAnchorCandidate
from mediamop.modules.refiner.file_remux_pass.visibility import (
    REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
    REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
)
from mediamop.modules.refiner.manager_queue_signals import file_is_owned_by_any_manager
from mediamop.modules.refiner.refiner_path_settings_service import RefinerPathRuntime
from mediamop.modules.refiner.refiner_remux_rules import is_refiner_media_candidate
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_evaluate import (
    fetch_manager_queue_signals_for_scan,
    merge_queue_views_for_watched_file,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_ops import (
    refiner_active_remux_pass_exists_for_relative_path,
    relative_posix_path_under_watched,
)
from mediamop.platform.activity import constants as activity_c
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.media_managers.manager_port import ManagerQueueSignal

logger = logging.getLogger(__name__)

_ACTIVITY_SCAN_LIMIT = 4000


def init_tv_season_cleanup_activity_fields(out: dict[str, Any]) -> None:
    out.setdefault("tv_season_folder_deleted", False)
    out.setdefault("tv_season_folder_path", None)
    out.setdefault("tv_season_folder_skip_reason", None)
    out.setdefault("tv_episode_check_summary", [])
    out.setdefault("tv_output_completeness_check", {})
    out.setdefault("tv_cascade_folders_deleted", [])
    out.setdefault("tv_manager_queue_unavailable", False)
    out.setdefault("source_deleted_after_success", False)


def get_tv_episode_set_media_files(*, season_folder: Path) -> list[Path]:
    """Direct-child media candidates only (same extensions as :func:`is_refiner_media_candidate`)."""

    if not season_folder.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(season_folder.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_file():
            continue
        if not is_refiner_media_candidate(child):
            continue
        found.append(child)
    return found


def _check_output_file_completeness_tv(*, output_file: Path, source_file: Path) -> dict[str, Any]:
    """Same minimum gate as Movies output check (duplicated intentionally — not shared cleanup code)."""

    if not output_file.is_file():
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": None,
            "source_size_bytes": None,
            "output_completeness_note": "The output file is missing at the path Refiner expected.",
        }
    try:
        out_sz = int(output_file.stat().st_size)
        src_sz = int(source_file.stat().st_size)
    except OSError as exc:
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": None,
            "source_size_bytes": None,
            "output_completeness_note": f"Refiner could not read the file size ({exc}).",
        }
    if out_sz <= 0:
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": out_sz,
            "source_size_bytes": src_sz,
            "output_completeness_note": "The output file is empty (zero bytes).",
        }
    if src_sz > 0 and out_sz < max(1, src_sz // 100):
        return {
            "output_completeness_check": "failed",
            "output_size_bytes": out_sz,
            "source_size_bytes": src_sz,
            "output_completeness_note": (
                "The output file is much smaller than the source (under 1% of source size), "
                "so Refiner blocked TV season cleanup as a safety step."
            ),
        }
    return {
        "output_completeness_check": "passed",
        "output_size_bytes": out_sz,
        "source_size_bytes": src_sz,
        "output_completeness_note": None,
    }


def _activity_documents_tv_live_success(session: Session, *, relative_posix: str) -> bool:
    """True when Activity retains a completed TV live pass with a successful terminal outcome for this path.

    ``refiner_jobs`` rows only carry the enqueue payload; terminal outcomes live in ``activity_events.detail`` JSON.
    """

    rows = session.scalars(
        select(ActivityEvent)
        .where(
            ActivityEvent.event_type == activity_c.REFINER_FILE_REMUX_PASS_COMPLETED,
            ActivityEvent.module == "refiner",
        )
        .order_by(ActivityEvent.id.desc())
        .limit(_ACTIVITY_SCAN_LIMIT),
    ).all()
    for row in rows:
        raw = (row.detail or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        rel = data.get("relative_media_path")
        if not isinstance(rel, str) or rel.strip() != relative_posix:
            continue
        scope = data.get("media_scope", "movie")
        if not isinstance(scope, str) or scope.strip().lower() != "tv":
            continue
        if data.get("dry_run") is True:
            continue
        if data.get("ok") is not True:
            continue
        outcome = data.get("outcome")
        if outcome not in (
            REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
            REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
        ):
            continue
        return True
    return False


def _episode_held_by_any_manager(
    *,
    signals: Sequence[ManagerQueueSignal],
    episode_path: Path,
) -> str | None:
    """The connection still holding this episode, or ``None``. Any manager is enough."""

    rows = merge_queue_views_for_watched_file(signals=signals, media_scope="tv", file_path=episode_path)
    candidate = FileAnchorCandidate(title=episode_path.stem, year=None)
    for row in rows:
        if file_is_owned_by_any_manager([row], candidate=candidate):
            return row.connection_label
    return None


def _tv_cascade_delete_empty_parents(
    *,
    first_parent: Path,
    watched_root: Path,
    cascade_folders_deleted: list[str],
) -> None:
    """Remove empty parents up to but not including watched_root (TV watched root is never deleted)."""

    root = watched_root.resolve()
    cur = first_parent.resolve()
    while cur != root:
        try:
            cur.relative_to(root)
        except ValueError:
            logger.warning(
                "Refiner TV cleanup: stopped cascade because a folder is outside the TV watched folder (%s).", cur
            )
            break
        if not cur.is_dir():
            break
        try:
            if any(cur.iterdir()):
                break
        except OSError:
            break
        try:
            cur.rmdir()
            cascade_folders_deleted.append(str(cur))
        except OSError as exc:
            logger.warning("Refiner TV cleanup: could not remove an empty parent folder (%s): %s", cur, exc)
            break
        cur = cur.parent


def handle_tv_cleanup_after_success(
    *,
    session: Session,
    settings: MediaMopSettings,
    path_runtime: RefinerPathRuntime,
    src: Path,
    watched_root: Path,
    out: dict[str, Any],
    dry_run: bool | None = None,
    min_file_age_seconds: int,
    current_job_id: int | None,
    remux_context: dict[str, Any],
    final_output_file: Path | None,
) -> None:
    """After a successful live TV pass: optional whole-season-folder removal + show cascade (gates in docstring)."""

    init_tv_season_cleanup_activity_fields(out)
    summary: list[str] = out["tv_episode_check_summary"]
    completeness: dict[str, str] = out["tv_output_completeness_check"]
    cascade: list[str] = out["tv_cascade_folders_deleted"]

    watched_resolved = watched_root.resolve()
    src_resolved = src.resolve()
    try:
        src_resolved.relative_to(watched_resolved)
    except ValueError:
        out["tv_season_folder_skip_reason"] = (
            "The video file is not under the saved TV watched folder, so nothing was removed."
        )
        summary.append("Stopped: the processed file is not under the TV watched folder.")
        return

    season_folder = src_resolved.parent
    try:
        season_folder.relative_to(watched_resolved)
    except ValueError:
        out["tv_season_folder_skip_reason"] = (
            "The season folder would sit outside the TV watched folder, so Refiner did nothing."
        )
        summary.append("Stopped: season folder is outside the TV watched folder.")
        return

    if season_folder.resolve() == watched_resolved:
        out["tv_season_folder_skip_reason"] = (
            "The video file sits directly in the TV watched folder root. Refiner does not delete the watched folder or "
            "treat the whole library as one season."
        )
        summary.append("Stopped: the season folder is the same as the TV watched folder root — nothing removed.")
        return

    out["tv_season_folder_path"] = str(season_folder)

    # Deleting a whole season folder is not something to do on a guess, so unlike the
    # watched-folder scan this gate refuses to run when any manager could not answer.
    signals, signal_report = fetch_manager_queue_signals_for_scan(session, settings, media_scope="tv")
    if signal_report.consulted == 0:
        out["tv_manager_queue_unavailable"] = True
        out["tv_season_folder_skip_reason"] = (
            "No media manager is connected for TV episodes, so MediaMop could not check whether anything is "
            "still importing. TV season cleanup was skipped so nothing was removed by mistake."
        )
        summary.append("Stopped: no media manager is connected for TV episodes.")
        return
    if not signal_report.all_reported:
        note = signal_report.silent_details[0]
        out["tv_manager_queue_unavailable"] = True
        out["tv_season_folder_skip_reason"] = f"{note} TV season cleanup was skipped so nothing was removed by mistake."
        summary.append(f"Stopped: import check failed — {note}")
        return

    episodes = get_tv_episode_set_media_files(season_folder=season_folder)
    if not episodes:
        out["tv_season_folder_skip_reason"] = (
            "This season folder has no direct video files Refiner treats as episodes, so nothing was removed."
        )
        summary.append("Stopped: no episode media files found as direct children of the season folder.")
        return

    out_dir = Path(path_runtime.output_folder).resolve()
    if not str(path_runtime.output_folder).strip():
        out["tv_season_folder_skip_reason"] = "No TV output folder is configured, so season cleanup was skipped."
        summary.append("Stopped: TV output folder is not configured.")
        return

    for ep in episodes:
        name = ep.name
        rel = relative_posix_path_under_watched(watched_root=watched_resolved, file_path=ep)
        line_parts: list[str] = [f"{name}:"]

        holder = _episode_held_by_any_manager(signals=signals, episode_path=ep)
        if holder is not None:
            msg = (
                f"{holder} is still working on at least one episode in this season ({name}), "
                "so the whole season folder was left in place."
            )
            out["tv_season_folder_skip_reason"] = msg
            line_parts.append(f"Import check failed — {holder} still lists this episode.")
            summary.append(" ".join(line_parts))
            return

        line_parts.append("Import check passed — no connected media manager still lists this episode.")

        if refiner_active_remux_pass_exists_for_relative_path(
            session,
            relative_posix=rel,
            media_scope="tv",
            exclude_job_id=current_job_id,
        ):
            msg = (
                f"Another Refiner TV job is already queued or running for {name}, "
                "so the whole season folder was left in place."
            )
            out["tv_season_folder_skip_reason"] = msg
            line_parts.append(
                "Active Refiner TV job check failed — a TV remux job is pending or running for this path."
            )
            summary.append(" ".join(line_parts))
            return
        line_parts.append(
            "Active Refiner TV job check passed — no other pending or running TV remux job for this path."
        )

        rel_eq = rel == str(remux_context.get("relative_media_path") or "").strip()
        live_ok = (
            remux_context.get("ok") is True
            and remux_context.get("dry_run") is False
            and remux_context.get("outcome")
            in (
                REMUX_PASS_OUTCOME_LIVE_OUTPUT_WRITTEN,
                REMUX_PASS_OUTCOME_LIVE_SKIPPED_NOT_REQUIRED,
            )
        )
        if rel_eq and live_ok:
            cand = final_output_file if rel_eq and final_output_file is not None else None
            if isinstance(cand, Path) and cand.is_file():
                expected_out = cand.resolve()
            else:
                of = remux_context.get("output_file")
                if isinstance(of, str) and of.strip():
                    expected_out = Path(of).resolve()
                else:
                    expected_out = (out_dir / Path(rel)).resolve()
            chk = _check_output_file_completeness_tv(output_file=expected_out, source_file=ep)
            completeness[name] = chk["output_completeness_check"]
            if chk["output_completeness_check"] != "passed":
                out["tv_season_folder_skip_reason"] = (
                    chk.get("output_completeness_note")
                    or f"Refiner expected a finished output file for {name}, but the safety check did not pass."
                )
                line_parts.append(
                    f"Output completeness check failed for this TV pass — {chk.get('output_completeness_note') or 'see logs'}.",
                )
                summary.append(" ".join(line_parts))
                return
            line_parts.append(
                "Refiner-processed check passed — this episode is the pass that just finished, "
                "and the output file passed the size checks.",
            )
        elif _activity_documents_tv_live_success(session, relative_posix=rel):
            expected_out = out_dir / Path(rel)
            chk = _check_output_file_completeness_tv(output_file=expected_out, source_file=ep)
            completeness[name] = chk["output_completeness_check"]
            if chk["output_completeness_check"] != "passed":
                out["tv_season_folder_skip_reason"] = (
                    chk.get("output_completeness_note")
                    or f"Refiner expected a finished output file for {name}, but the safety check did not pass."
                )
                line_parts.append(
                    f"Output completeness check failed for a previously finished Refiner TV pass — {chk.get('output_completeness_note') or 'see logs'}.",
                )
                summary.append(" ".join(line_parts))
                return
            line_parts.append(
                "Refiner-processed check passed — a successful live TV pass is on record and the output file passed the size checks.",
            )
        else:
            try:
                age_s = time.time() - float(ep.stat().st_mtime)
            except OSError:
                age_s = -1
            min_age = max(0, int(min_file_age_seconds))
            if min_age > 0 and age_s < min_age:
                out["tv_season_folder_skip_reason"] = (
                    f"Episode {name} was never finished by Refiner in TV mode and is newer than the minimum age "
                    f"({min_age}s), so the season folder was left in place."
                )
                line_parts.append(
                    f"Never-processed check failed — file is not old enough yet (minimum {min_age}s since last change).",
                )
                summary.append(" ".join(line_parts))
                return
            completeness[name] = "skipped"
            line_parts.append(
                "Never-processed check passed — Refiner has no successful live TV pass on record for this file, "
                "no connected media manager still lists it, and the file is old enough under your minimum-age setting.",
            )

        summary.append(" ".join(line_parts))

    try:
        shutil.rmtree(season_folder)
    except OSError as exc:
        locked = getattr(exc, "filename", None)
        human = (
            f"A file or folder could not be removed because the system reported it is in use or locked: {locked or season_folder}. "
            "The whole season folder was left in place."
        )
        out["tv_season_folder_skip_reason"] = human
        summary.append(f"Deletion failed: {human}")
        logger.warning("Refiner TV cleanup: %s", human)
        return

    out["tv_season_folder_deleted"] = True
    out["source_deleted_after_success"] = True
    out["tv_season_folder_skip_reason"] = None
    summary.append(f"Removed the whole season folder: {season_folder}")

    _tv_cascade_delete_empty_parents(
        first_parent=season_folder.resolve().parent,
        watched_root=watched_resolved,
        cascade_folders_deleted=cascade,
    )


__all__ = [
    "get_tv_episode_set_media_files",
    "handle_tv_cleanup_after_success",
    "init_tv_season_cleanup_activity_fields",
]
