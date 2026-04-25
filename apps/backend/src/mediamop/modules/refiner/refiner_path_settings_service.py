"""Refiner path settings — singleton row validation, resolution, and remux runtime bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow

RefinerMediaScope = Literal["movie", "tv"]

_REFINER_LEGACY_WINDOWS_MOVIE_WORK = Path(r"C:\ProgramData\Media\refiner-movie-work")
_REFINER_LEGACY_WINDOWS_TV_WORK = Path(r"C:\ProgramData\MediaMop\refiner-tv-work")


def resolved_default_refiner_work_folder(*, mediamop_home: str) -> str:
    """Default Movies work/temp directory.

    Defaults are under ``MEDIAMOP_HOME`` so packaged Windows installs use
    ``C:\\ProgramData\\MediaMop`` while Docker/dev installs follow their configured
    runtime root.
    """

    return str(Path(mediamop_home).expanduser().resolve() / "refiner" / "refiner-movie-work")


def resolved_default_refiner_tv_work_folder(*, mediamop_home: str) -> str:
    """Default TV work/temp directory (separate from Movies).

    Defaults are under ``MEDIAMOP_HOME`` so packaged Windows installs use
    ``C:\\ProgramData\\MediaMop`` while Docker/dev installs follow their configured
    runtime root.
    """

    return str(Path(mediamop_home).expanduser().resolve() / "refiner" / "refiner-tv-work")


def _is_legacy_refiner_default_work_folder(raw: str, *, media_scope: RefinerMediaScope) -> bool:
    candidate = Path(raw).expanduser()
    legacy = _REFINER_LEGACY_WINDOWS_TV_WORK if media_scope == "tv" else _REFINER_LEGACY_WINDOWS_MOVIE_WORK
    return str(candidate).rstrip("\\/").lower() == str(legacy).rstrip("\\/").lower()


def _norm_dir_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def _is_same_or_nested(a: Path, b: Path) -> bool:
    ar, br = a.resolve(), b.resolve()
    if ar == br:
        return True
    try:
        ar.relative_to(br)
        return True
    except ValueError:
        pass
    try:
        br.relative_to(ar)
        return True
    except ValueError:
        return False


def _validate_path_separation(*, watched: Path | None, work: Path, output: Path | None) -> None:
    if output is not None:
        if _is_same_or_nested(work, output):
            msg = "Refiner work/temp folder and output folder must be separate (no overlap or containment)."
            raise ValueError(msg)
        if watched is not None and _is_same_or_nested(watched, output):
            msg = "Refiner watched folder and output folder must be separate (no overlap or containment)."
            raise ValueError(msg)
    if watched is not None and _is_same_or_nested(watched, work):
        msg = "Refiner watched folder and work/temp folder must be separate (no overlap or containment)."
        raise ValueError(msg)


def _clamp_watched_folder_poll_interval_seconds(raw: int) -> int:
    """How often the in-process scheduler re-checks periodic scan timing for a scope (10s–7d)."""

    return max(10, min(int(raw), 7 * 24 * 3600))


def _validate_cross_family_paths(paths: list[Path]) -> None:
    """Movie vs TV trees must not overlap (confusing relative roots and temp/output collisions)."""

    resolved = [p.resolve() for p in paths]
    for i, a in enumerate(resolved):
        for b in resolved[i + 1 :]:
            if _is_same_or_nested(a, b):
                msg = (
                    "Refiner Movies and TV folder paths must not overlap or contain one another. "
                    "Use separate directory trees (for example different top-level library folders)."
                )
                raise ValueError(msg)


def effective_work_folder(*, row: RefinerPathSettingsRow, mediamop_home: str) -> tuple[str, bool]:
    """Return ``(absolute_work_path, is_default)`` for movie scope."""

    stored = (row.refiner_work_folder or "").strip()
    if stored:
        if _is_legacy_refiner_default_work_folder(stored, media_scope="movie"):
            return resolved_default_refiner_work_folder(mediamop_home=mediamop_home), True
        return stored, False
    return resolved_default_refiner_work_folder(mediamop_home=mediamop_home), True


def effective_tv_work_folder(*, row: RefinerPathSettingsRow, mediamop_home: str) -> tuple[str, bool]:
    """Return ``(absolute_tv_work_path, is_default)``."""

    stored = (row.refiner_tv_work_folder or "").strip()
    if stored:
        if _is_legacy_refiner_default_work_folder(stored, media_scope="tv"):
            return resolved_default_refiner_tv_work_folder(mediamop_home=mediamop_home), True
        return stored, False
    return resolved_default_refiner_tv_work_folder(mediamop_home=mediamop_home), True


def ensure_refiner_path_settings_row(session: Session) -> RefinerPathSettingsRow:
    """Return singleton row ``id = 1`` (seeded by initial Alembic revision on greenfield DBs)."""

    row = session.get(RefinerPathSettingsRow, 1)
    if row is None:
        msg = "refiner_path_settings row missing — run database migrations (alembic upgrade head)."
        raise RuntimeError(msg)
    return row


@dataclass(frozen=True, slots=True)
class RefinerPathRuntime:
    """Resolved folders for ``refiner.file.remux_pass.v1`` (no environment path fallback)."""

    watched_folder: str
    output_folder: str
    work_folder_effective: str
    work_folder_is_default: bool
    preview_output_folder: str | None = None


def _normalize_media_scope(raw: str | None) -> RefinerMediaScope:
    s = (raw or "movie").strip().lower()
    if s == "tv":
        return "tv"
    return "movie"


def resolve_refiner_path_runtime_for_remux(
    session: Session,
    settings: MediaMopSettings,
    *,
    dry_run: bool | None = None,
    media_scope: str | None = "movie",
) -> tuple[RefinerPathRuntime | None, str | None]:
    """Build runtime paths; on error return ``(None, reason)``."""

    scope = _normalize_media_scope(media_scope)
    label = "TV Refiner" if scope == "tv" else "Movies Refiner"
    row = ensure_refiner_path_settings_row(session)

    if scope == "tv":
        watched_raw = (row.refiner_tv_watched_folder or "").strip()
        watched_col = "refiner_tv_watched_folder"
    else:
        watched_raw = (row.refiner_watched_folder or "").strip()
        watched_col = "refiner_watched_folder"

    if not watched_raw:
        return None, (
            f"{label} watched folder is not set in saved path settings. "
            "Manual remux and folder-scan jobs for this scope need a watched folder to resolve relative paths. "
            f"Configure {label.lower()} paths (column {watched_col}) before enqueueing or running those jobs."
        )
    watched_path = _norm_dir_path(watched_raw)
    if not watched_path.is_dir():
        return None, f"{label} watched folder must be an existing directory (update saved path settings)."

    if scope == "tv":
        work_str, work_is_default = effective_tv_work_folder(row=row, mediamop_home=settings.mediamop_home)
    else:
        work_str, work_is_default = effective_work_folder(row=row, mediamop_home=settings.mediamop_home)
    work_path = _norm_dir_path(work_str)

    if scope == "tv":
        out_raw = (row.refiner_tv_output_folder or "").strip()
    else:
        out_raw = (row.refiner_output_folder or "").strip()
    if not out_raw:
        return None, (
            f"Configure the {label.lower()} output folder in saved Refiner path settings "
            "before running a live remux pass for this scope."
        )
    output_path = _norm_dir_path(out_raw)
    if not output_path.is_dir():
        return None, f"{label} output folder must be an existing directory (update saved path settings)."

    try:
        _validate_path_separation(watched=watched_path, work=work_path, output=output_path)
    except ValueError as exc:
        return None, str(exc)

    if not work_is_default and not work_path.is_dir():
        return None, f"{label} work/temp folder must be an existing directory when set to a custom path."

    return (
        RefinerPathRuntime(
            watched_folder=str(watched_path),
            output_folder=str(output_path),
            work_folder_effective=str(work_path),
            work_folder_is_default=work_is_default,
        ),
        None,
    )


def build_refiner_path_settings_get_out(*, row: RefinerPathSettingsRow, settings: MediaMopSettings) -> dict[str, object]:
    work_eff, _is_def = effective_work_folder(row=row, mediamop_home=settings.mediamop_home)
    default_work = resolved_default_refiner_work_folder(mediamop_home=settings.mediamop_home)
    tv_work_eff, _tv_def = effective_tv_work_folder(row=row, mediamop_home=settings.mediamop_home)
    default_tv_work = resolved_default_refiner_tv_work_folder(mediamop_home=settings.mediamop_home)
    return {
        "refiner_watched_folder": row.refiner_watched_folder,
        "refiner_watched_folder_exists": bool((row.refiner_watched_folder or "").strip() and Path(row.refiner_watched_folder).is_dir()),
        "refiner_work_folder": row.refiner_work_folder,
        "refiner_output_folder": (row.refiner_output_folder or "").strip() or None,
        "resolved_default_work_folder": default_work,
        "effective_work_folder": work_eff,
        "refiner_tv_watched_folder": row.refiner_tv_watched_folder,
        "refiner_tv_watched_folder_exists": bool(
            (row.refiner_tv_watched_folder or "").strip() and Path(row.refiner_tv_watched_folder).is_dir()
        ),
        "refiner_tv_work_folder": row.refiner_tv_work_folder,
        "refiner_tv_output_folder": (row.refiner_tv_output_folder or "").strip() or None,
        "resolved_default_tv_work_folder": default_tv_work,
        "effective_tv_work_folder": tv_work_eff,
        "movie_watched_folder_check_interval_seconds": _clamp_watched_folder_poll_interval_seconds(
            int(row.movie_watched_folder_check_interval_seconds)
        ),
        "tv_watched_folder_check_interval_seconds": _clamp_watched_folder_poll_interval_seconds(
            int(row.tv_watched_folder_check_interval_seconds)
        ),
        "updated_at": row.updated_at,
    }


def _tv_paths_for_overlap_check(
    *,
    row: RefinerPathSettingsRow,
    settings: MediaMopSettings,
) -> list[Path]:
    """Material TV paths from the persisted row (for cross-family validation)."""

    if not (row.refiner_tv_watched_folder or "").strip() and not (row.refiner_tv_output_folder or "").strip():
        return []
    out: list[Path] = []
    tw = (row.refiner_tv_watched_folder or "").strip()
    if tw:
        out.append(_norm_dir_path(tw))
    tout = (row.refiner_tv_output_folder or "").strip()
    if tout:
        out.append(_norm_dir_path(tout))
    tw_eff, _ = effective_tv_work_folder(row=row, mediamop_home=settings.mediamop_home)
    out.append(_norm_dir_path(tw_eff))
    return out


def apply_refiner_path_settings_put(
    session: Session,
    settings: MediaMopSettings,
    *,
    watched_folder: str | None,
    work_folder: str | None,
    output_folder: str | None,
    tv_paths_included: bool = False,
    tv_watched_folder: str | None = None,
    tv_work_folder: str | None = None,
    tv_output_folder: str | None = None,
    movie_watched_folder_check_interval_seconds: int | None = None,
    tv_watched_folder_check_interval_seconds: int | None = None,
) -> RefinerPathSettingsRow:
    """Validate and persist path settings (hard-block invalid overlap on save)."""

    row = ensure_refiner_path_settings_row(session)

    watched_clean = (watched_folder or "").strip() or None
    watched_path: Path | None = None
    watched_store: str | None = None
    if watched_clean is not None:
        watched_path = _norm_dir_path(watched_clean)
        watched_store = str(watched_path)

    out_clean = (output_folder or "").strip()
    output_path: Path | None = None
    if watched_clean is not None and not out_clean:
        msg = "Movies Refiner output folder is required when a Movies watched folder is set."
        raise ValueError(msg)
    if out_clean:
        output_path = _norm_dir_path(out_clean)
        if not output_path.is_dir():
            msg = "Movies Refiner output folder must already exist on disk."
            raise ValueError(msg)

    work_in = (work_folder if work_folder is not None else "").strip()
    if not work_in:
        work_resolved = resolved_default_refiner_work_folder(mediamop_home=settings.mediamop_home)
        work_path = _norm_dir_path(work_resolved)
        work_path.mkdir(parents=True, exist_ok=True)
        stored_work = str(work_path)
    else:
        work_path = _norm_dir_path(work_in)
        if not work_path.is_dir():
            msg = "Movies Refiner work/temp folder must already exist on disk when set to a custom path."
            raise ValueError(msg)
        stored_work = str(work_path)

    _validate_path_separation(watched=watched_path, work=work_path, output=output_path)

    cross_paths: list[Path] = [work_path]
    if output_path is not None:
        cross_paths.append(output_path)
    if watched_path is not None:
        cross_paths.append(watched_path)

    if tv_paths_included:
        tw_clean = (tv_watched_folder or "").strip() or None
        tout_in = (tv_output_folder if tv_output_folder is not None else "").strip()
        twork_in = (tv_work_folder if tv_work_folder is not None else "").strip()

        if tw_clean is None and not tout_in and not twork_in:
            row.refiner_tv_watched_folder = None
            row.refiner_tv_work_folder = None
            row.refiner_tv_output_folder = None
        else:
            if tw_clean is None and tout_in:
                msg = "Set a TV watched folder before saving a TV output folder."
                raise ValueError(msg)
            if tw_clean is None:
                msg = "TV Refiner paths: set a watched folder (or clear all TV fields)."
                raise ValueError(msg)
            tv_watched_path = _norm_dir_path(tw_clean)
            tw_store = str(tv_watched_path)

            if not tout_in:
                msg = "TV Refiner output folder is required when a TV watched folder is set."
                raise ValueError(msg)
            tv_output_path = _norm_dir_path(tout_in)
            if not tv_output_path.is_dir():
                msg = "TV Refiner output folder must already exist on disk."
                raise ValueError(msg)

            if not twork_in:
                tv_work_resolved = resolved_default_refiner_tv_work_folder(mediamop_home=settings.mediamop_home)
                tv_work_path = _norm_dir_path(tv_work_resolved)
                tv_work_path.mkdir(parents=True, exist_ok=True)
                stored_tv_work = str(tv_work_path)
            else:
                tv_work_path = _norm_dir_path(twork_in)
                if not tv_work_path.is_dir():
                    msg = "TV Refiner work/temp folder must already exist on disk when set to a custom path."
                    raise ValueError(msg)
                stored_tv_work = str(tv_work_path)

            _validate_path_separation(watched=tv_watched_path, work=tv_work_path, output=tv_output_path)

            row.refiner_tv_watched_folder = tw_store
            row.refiner_tv_work_folder = stored_tv_work
            row.refiner_tv_output_folder = str(tv_output_path)

            cross_paths.extend([tv_watched_path, tv_work_path, tv_output_path])
    else:
        cross_paths.extend(_tv_paths_for_overlap_check(row=row, settings=settings))

    _validate_cross_family_paths(cross_paths)

    row.refiner_watched_folder = watched_store
    row.refiner_work_folder = stored_work
    row.refiner_output_folder = str(output_path) if output_path is not None else ""
    if movie_watched_folder_check_interval_seconds is not None:
        row.movie_watched_folder_check_interval_seconds = _clamp_watched_folder_poll_interval_seconds(
            movie_watched_folder_check_interval_seconds
        )
    if tv_watched_folder_check_interval_seconds is not None:
        row.tv_watched_folder_check_interval_seconds = _clamp_watched_folder_poll_interval_seconds(
            tv_watched_folder_check_interval_seconds
        )
    session.add(row)
    session.flush()
    return row
