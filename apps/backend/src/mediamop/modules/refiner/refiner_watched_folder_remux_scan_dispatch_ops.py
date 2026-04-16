"""Filesystem scan helpers and duplicate guards for watched-folder remux scan dispatch."""

from __future__ import annotations

import json
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.refiner_remux_rules import is_refiner_media_candidate


def iter_watched_folder_media_candidate_files(watched_root: Path, *, min_file_age_seconds: int = 0) -> list[Path]:
    """Sorted candidate files under ``watched_root`` honoring optional minimum file-age guardrail."""

    root = watched_root.resolve()
    now = time.time()
    min_age = max(0, int(min_file_age_seconds))
    found: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if not is_refiner_media_candidate(p):
            continue
        try:
            p.resolve().relative_to(root)
        except ValueError:
            continue
        if min_age > 0:
            try:
                age_s = now - float(p.stat().st_mtime)
            except OSError:
                continue
            if age_s < min_age:
                continue
        found.append(p)
    return found


def relative_posix_path_under_watched(*, watched_root: Path, file_path: Path) -> str:
    return file_path.resolve().relative_to(watched_root.resolve()).as_posix()


def refiner_active_remux_pass_exists_for_relative_path(
    session: Session,
    *,
    relative_posix: str,
    media_scope: str = "movie",
    exclude_job_id: int | None = None,
) -> bool:
    """True when a pending or leased ``refiner.file.remux_pass.v1`` row already carries this relative path + scope."""

    want_scope = media_scope if media_scope in ("movie", "tv") else "movie"
    rows = session.scalars(
        select(RefinerJob).where(
            RefinerJob.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND,
            RefinerJob.status.in_(
                (
                    RefinerJobStatus.PENDING.value,
                    RefinerJobStatus.LEASED.value,
                ),
            ),
        ),
    ).all()
    for job in rows:
        if exclude_job_id is not None and int(job.id) == int(exclude_job_id):
            continue
        raw = (job.payload_json or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        rel = data.get("relative_media_path")
        job_scope = data.get("media_scope", "movie")
        if not isinstance(job_scope, str) or job_scope not in ("movie", "tv"):
            job_scope = "movie"
        if isinstance(rel, str) and rel.strip() == relative_posix and job_scope == want_scope:
            return True
    return False
