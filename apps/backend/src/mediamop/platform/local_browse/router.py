"""Operator-only server-side filesystem browsing for path settings."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette import status

from mediamop.platform.auth.authorization import RequireOperatorDep

router = APIRouter(tags=["system"])


class DirectoryBrowseEntry(BaseModel):
    name: str
    path: str
    kind: str
    description: str | None = None


class DirectoryBrowseOut(BaseModel):
    current_path: str | None
    parent_path: str | None
    entries: list[DirectoryBrowseEntry]


def _normalize_directory_path(path: str) -> str:
    full = Path(path).expanduser().resolve(strict=False)
    value = str(full)
    if os.name == "nt":
        return value.rstrip("\\/") + "\\"
    return value


def _list_root_entries() -> list[DirectoryBrowseEntry]:
    if os.name == "nt":
        import string

        entries: list[DirectoryBrowseEntry] = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if not os.path.isdir(root):
                continue
            description = "Drive"
            try:
                import ctypes

                drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)
                description = {
                    2: "External drive",
                    3: "Local drive",
                    4: "Network drive",
                    5: "Optical drive",
                    6: "RAM disk",
                }.get(int(drive_type), "Drive")
            except Exception:
                description = "Drive"
            entries.append(DirectoryBrowseEntry(name=root.rstrip("\\"), path=root, kind="root", description=description))
        return entries
    return [DirectoryBrowseEntry(name="/", path="/", kind="root", description="Filesystem root")]


@router.get("/system/directories", response_model=DirectoryBrowseOut)
def get_system_directories(
    _user: RequireOperatorDep,
    path: str | None = None,
) -> DirectoryBrowseOut:
    """List server-visible folders for the in-app path browser."""

    if path is None or not path.strip():
        return DirectoryBrowseOut(current_path=None, parent_path=None, entries=_list_root_entries())

    normalized = _normalize_directory_path(path)
    if not os.path.isdir(normalized):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The requested directory does not exist.")

    parent = Path(normalized).parent
    parent_path = str(parent) if str(parent) != normalized else None
    if os.name == "nt" and parent_path:
        parent_path = parent_path.rstrip("\\/") + "\\"

    entries: list[DirectoryBrowseEntry] = []
    try:
        for child in Path(normalized).iterdir():
            if not child.is_dir():
                continue
            entries.append(
                DirectoryBrowseEntry(
                    name=child.name or str(child),
                    path=_normalize_directory_path(str(child)),
                    kind="directory",
                    description=None,
                ),
            )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MediaMop cannot access this folder.") from exc
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    entries.sort(key=lambda entry: entry.name.lower())
    return DirectoryBrowseOut(current_path=normalized, parent_path=parent_path, entries=entries)
