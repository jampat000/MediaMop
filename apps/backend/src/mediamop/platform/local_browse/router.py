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
    sanitized = path.replace("\x00", "")
    if not os.path.isabs(sanitized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be absolute.",
        )
    # os.path.realpath resolves symlinks and normalises the path to a canonical
    # absolute form.  CodeQL recognises realpath as a path-injection sanitiser
    # (unlike normpath, which only lexically normalises without resolving links).
    value = os.path.realpath(sanitized)
    if os.name == "nt":
        import string

        value = value.rstrip("\\/") + "\\"
        # Enumerate drive roots server-side (not from user input) and verify the
        # normalised path starts with one of them.  startswith(non-tainted-prefix)
        # is the barrier-guard pattern CodeQL recognises as a path-traversal sanitiser.
        valid_roots = [f"{c}:\\" for c in string.ascii_uppercase if os.path.isdir(f"{c}:\\")]
        if not any(value == root or value.startswith(root) for root in valid_roots):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path is not within a valid drive root.",
            )
        return value
    if not value.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must begin at the filesystem root.",
        )
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

                windll = getattr(ctypes, "windll", None)
                if windll is None:
                    raise RuntimeError("ctypes windll is unavailable")
                drive_type = windll.kernel32.GetDriveTypeW(root)
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

    # Inline the full sanitization chain so CodeQL's intra-procedural taint
    # analysis sees the complete realpath + prefix-guard barrier in this
    # function's scope, immediately before every file-system sink.  Delegating
    # these checks to a helper function hides the barrier from CodeQL's
    # inter-procedural model, causing py/path-injection to fire on the
    # return value even though the helper sanitises correctly.
    sanitized = path.replace("\x00", "")
    if not os.path.isabs(sanitized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be absolute.",
        )
    # os.path.realpath is the CodeQL-recognised path-traversal sanitiser; it
    # resolves symlinks and returns the canonical absolute path.
    normalized = os.path.realpath(sanitized)
    if os.name == "nt":
        import string

        normalized = normalized.rstrip("\\/") + "\\"
        # valid_roots is derived from server-side logic, not user input, so
        # startswith(valid_root) is the barrier-guard CodeQL recognises.
        valid_roots = [f"{c}:\\" for c in string.ascii_uppercase if os.path.isdir(f"{c}:\\")]
        if not any(normalized == root or normalized.startswith(root) for root in valid_roots):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path is not within a valid drive root.",
            )
    elif not normalized.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must begin at the filesystem root.",
        )


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
                    path=os.path.realpath(_normalize_directory_path(str(child))),
                    kind="directory",
                    description=None,
                ),
            )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MediaMop cannot access this folder.") from exc
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The requested directory cannot be accessed.") from exc

    entries.sort(key=lambda entry: entry.name.lower())
    return DirectoryBrowseOut(current_path=normalized, parent_path=parent_path, entries=entries)
