"""Safe resolution of operator-supplied media paths under the saved Refiner watched folder."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


def resolve_media_file_under_refiner_root(*, media_root: str, relative_path: str) -> Path:
    """Return ``(root / relative).resolve()`` only when the result stays under ``root.resolve()``."""

    root = Path(media_root).expanduser().resolve()
    if not root.is_dir():
        msg = "Refiner watched folder (saved settings) must be an existing directory"
        raise ValueError(msg)
    rel = (relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel:
        msg = "relative_media_path is required"
        raise ValueError(msg)
    parts = PurePosixPath(rel).parts
    if ".." in parts or rel.startswith(".."):
        msg = "relative_media_path must not contain parent segments"
        raise ValueError(msg)
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        msg = "resolved file path escapes the saved Refiner watched folder"
        raise ValueError(msg) from exc
    return candidate
