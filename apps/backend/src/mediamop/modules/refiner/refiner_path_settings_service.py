"""Refiner path settings — singleton row validation, resolution, and remux runtime bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_path_settings_model import RefinerPathSettingsRow


def resolved_default_refiner_work_folder(*, mediamop_home: str) -> str:
    """Canonical default work/temp directory under ``MEDIAMOP_HOME`` (runtime data, not the repo)."""

    return str((Path(mediamop_home).expanduser().resolve() / "refiner" / "work"))


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


def _validate_path_separation(*, watched: Path | None, work: Path, output: Path) -> None:
    if _is_same_or_nested(work, output):
        msg = "Refiner work/temp folder and output folder must be separate (no overlap or containment)."
        raise ValueError(msg)
    if watched is None:
        return
    if _is_same_or_nested(watched, output):
        msg = "Refiner watched folder and output folder must be separate (no overlap or containment)."
        raise ValueError(msg)
    if _is_same_or_nested(watched, work):
        msg = "Refiner watched folder and work/temp folder must be separate (no overlap or containment)."
        raise ValueError(msg)


def effective_work_folder(*, row: RefinerPathSettingsRow, mediamop_home: str) -> tuple[str, bool]:
    """Return ``(absolute_work_path, is_default)``."""

    stored = (row.refiner_work_folder or "").strip()
    if stored:
        return stored, False
    return resolved_default_refiner_work_folder(mediamop_home=mediamop_home), True


def ensure_refiner_path_settings_row(session: Session) -> RefinerPathSettingsRow:
    """Return singleton row ``id = 1`` (created by Alembic migration ``0011_refiner_path_settings``)."""

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


def resolve_refiner_path_runtime_for_remux(
    session: Session,
    settings: MediaMopSettings,
    *,
    dry_run: bool,
) -> tuple[RefinerPathRuntime | None, str | None]:
    """Build runtime paths; on error return ``(None, reason)``."""

    row = ensure_refiner_path_settings_row(session)
    watched_raw = (row.refiner_watched_folder or "").strip()
    if not watched_raw:
        return None, (
            "Refiner watched folder is not set in saved path settings. "
            "Manual refiner.file.remux_pass.v1 jobs require it to resolve relative_media_path and for bounded source cleanup. "
            "You can save other Refiner paths without a watched folder, but configure the watched folder before enqueueing or running those jobs."
        )
    watched_path = _norm_dir_path(watched_raw)
    if not watched_path.is_dir():
        return None, "Refiner watched folder must be an existing directory (update saved path settings)."

    work_str, work_is_default = effective_work_folder(row=row, mediamop_home=settings.mediamop_home)
    work_path = _norm_dir_path(work_str)

    if dry_run:
        return (
            RefinerPathRuntime(
                watched_folder=str(watched_path),
                output_folder="",
                work_folder_effective=str(work_path),
                work_folder_is_default=work_is_default,
            ),
            None,
        )

    out_raw = (row.refiner_output_folder or "").strip()
    if not out_raw:
        return None, (
            "Configure the Refiner output folder in saved Refiner path settings before running a live remux pass."
        )
    output_path = _norm_dir_path(out_raw)
    if not output_path.is_dir():
        return None, "Refiner output folder must be an existing directory (update saved path settings)."

    try:
        _validate_path_separation(watched=watched_path, work=work_path, output=output_path)
    except ValueError as exc:
        return None, str(exc)

    if not work_is_default and not work_path.is_dir():
        return None, "Refiner work/temp folder must be an existing directory when set to a custom path."

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
    return {
        "refiner_watched_folder": row.refiner_watched_folder,
        "refiner_work_folder": row.refiner_work_folder,
        "refiner_output_folder": row.refiner_output_folder,
        "resolved_default_work_folder": default_work,
        "effective_work_folder": work_eff,
        "updated_at": row.updated_at,
    }


def apply_refiner_path_settings_put(
    session: Session,
    settings: MediaMopSettings,
    *,
    watched_folder: str | None,
    work_folder: str | None,
    output_folder: str,
) -> RefinerPathSettingsRow:
    """Validate and persist path settings (hard-block invalid overlap on save)."""

    row = ensure_refiner_path_settings_row(session)

    watched_clean = (watched_folder or "").strip() or None
    watched_path: Path | None = None
    watched_store: str | None = None
    if watched_clean is not None:
        watched_path = _norm_dir_path(watched_clean)
        if not watched_path.is_dir():
            msg = "Refiner watched folder must already exist on disk when set."
            raise ValueError(msg)
        watched_store = str(watched_path)

    out_clean = output_folder.strip()
    if not out_clean:
        msg = "Refiner output folder is required (non-empty path)."
        raise ValueError(msg)
    output_path = _norm_dir_path(out_clean)
    if not output_path.is_dir():
        msg = "Refiner output folder must already exist on disk."
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
            msg = "Refiner work/temp folder must already exist on disk when set to a custom path."
            raise ValueError(msg)
        stored_work = str(work_path)

    _validate_path_separation(watched=watched_path, work=work_path, output=output_path)

    row.refiner_watched_folder = watched_store
    row.refiner_work_folder = stored_work
    row.refiner_output_folder = str(output_path)
    session.add(row)
    session.flush()
    return row
