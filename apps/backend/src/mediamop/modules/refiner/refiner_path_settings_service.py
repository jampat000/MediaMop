"""Refiner library folders: validation and the runtime bundle a remux pass resolves from a library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_library_service import resolve_library, seeded_library_for_scope

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


@dataclass(frozen=True, slots=True)
class RefinerPathRuntime:
    """Resolved folders for ``refiner.file.remux_pass.v1`` (no environment path fallback)."""

    watched_folder: str
    output_folder: str
    work_folder_effective: str
    work_folder_is_default: bool
    preview_output_folder: str | None = None
    #: Output-side library settings. They travel with the paths because the pass already
    #: receives this and they are decisions about the same output folder (#344).
    sidecar_patterns_csv: str = ""
    preserve_original_timestamps: bool = False
    #: What to do when an output already exists at this path. "replace" is what every
    #: install does today (#349).
    output_collision_policy: str = "replace"
    hardware_decode_mode: str = "off"
    hardware_device: str = ""
    hardware_disabled_vendors_csv: str = ""
    ffmpeg_strictness: str = "normal"


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
    library_id: int | None = None,
) -> tuple[RefinerPathRuntime | None, str | None]:
    """Build runtime paths for a library; on error return ``(None, reason)``.

    Reads ``refiner_libraries`` rather than the ``refiner_path_settings`` singleton
    (ADR-0014). ``media_scope`` still selects which library when a caller has no
    ``library_id`` — a payload queued before the upgrade, for instance.
    """

    library = resolve_library(session, library_id=library_id, media_scope=media_scope)
    if library is None:
        # There is one store now (#363). A database with no library covering this scope
        # is one an operator has emptied, not an unmigrated one — 0011 seeds Movies and
        # TV — so this refuses with a sentence rather than falling back to a table that
        # no longer exists.
        scope = _normalize_media_scope(media_scope)
        label = "TV" if scope == "tv" else "Movies"
        return None, (
            f"No Refiner library covers {label}. Add one on the Refiner Libraries settings page, "
            "then queue this work again."
        )
    return resolve_refiner_path_runtime_for_library(settings, library)


def resolve_refiner_path_runtime_for_library(
    settings: MediaMopSettings,
    library: RefinerLibraryRow,
) -> tuple[RefinerPathRuntime | None, str | None]:
    """Resolve one library's folders, or say why they cannot be used."""

    label = library.name.strip() or ("TV Refiner" if library.media_type == "tv" else "Movies Refiner")

    watched_raw = (library.watched_folder or "").strip()
    if not watched_raw:
        return None, (
            f"The {label} library has no watched folder set. "
            "Manual remux and folder-scan jobs need a watched folder to resolve relative paths. "
            "Set it on the Refiner Libraries settings page before enqueueing or running those jobs."
        )
    watched_path = _norm_dir_path(watched_raw)
    if not watched_path.is_dir():
        return None, f"The {label} library's watched folder must be an existing directory."

    work_str, work_is_default = effective_library_work_folder(library=library, mediamop_home=settings.mediamop_home)
    work_path = _norm_dir_path(work_str)

    out_raw = (library.output_folder or "").strip()
    if not out_raw:
        return None, (
            f"The {label} library has no output folder set. "
            "Set it on the Refiner Libraries settings page before running a live remux pass."
        )
    output_path = _norm_dir_path(out_raw)
    if not output_path.is_dir():
        return None, f"The {label} library's output folder must be an existing directory."

    try:
        _validate_path_separation(watched=watched_path, work=work_path, output=output_path)
    except ValueError as exc:
        return None, str(exc)

    if not work_is_default and not work_path.is_dir():
        return None, f"The {label} library's work/temp folder must be an existing directory when set to a custom path."

    return (
        RefinerPathRuntime(
            watched_folder=str(watched_path),
            output_folder=str(output_path),
            work_folder_effective=str(work_path),
            work_folder_is_default=work_is_default,
            sidecar_patterns_csv=library.sidecar_patterns_csv or "",
            preserve_original_timestamps=bool(library.preserve_original_timestamps),
            output_collision_policy=library.output_collision_policy or "replace",
            hardware_decode_mode=library.hardware_decode_mode or "off",
            hardware_device=library.hardware_device or "",
            hardware_disabled_vendors_csv=library.hardware_disabled_vendors_csv or "",
            ffmpeg_strictness=library.ffmpeg_strictness or "normal",
        ),
        None,
    )


def effective_library_work_folder(*, library: RefinerLibraryRow, mediamop_home: str) -> tuple[str, bool]:
    """A library's work folder, falling back to the per-scope default it used to use."""

    raw = (library.work_folder or "").strip()
    scope = (library.media_type or "movie").strip().lower()
    if not raw or _is_legacy_refiner_default_work_folder(raw, media_scope=scope):  # type: ignore[arg-type]
        default = (
            resolved_default_refiner_tv_work_folder(mediamop_home=mediamop_home)
            if scope == "tv"
            else resolved_default_refiner_work_folder(mediamop_home=mediamop_home)
        )
        return default, True
    return raw, False
