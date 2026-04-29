"""Recoverable file writes, moves, and deletes for media mutations."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path


class FileLifecycleError(RuntimeError):
    """Raised when a guarded filesystem mutation cannot complete safely."""


def safe_copy_to_final(*, source: Path, final: Path) -> None:
    """Copy ``source`` to ``final`` without exposing a partial destination file."""

    src = source.resolve()
    dst = final
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".partial", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except Exception as exc:
        _best_effort_unlink(tmp)
        raise FileLifecycleError(f"Could not safely copy {src} to {dst}: {exc}") from exc


def try_hardlink_to_final(*, source: Path, final: Path) -> bool:
    """Atomically expose ``final`` as a hardlink to ``source`` when the filesystem supports it."""

    src = source.resolve()
    dst = final
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".link", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    _best_effort_unlink(tmp)
    try:
        os.link(src, tmp)
        os.replace(tmp, dst)
        return True
    except OSError:
        _best_effort_unlink(tmp)
        return False


def safe_finalize_file(*, staged: Path, final: Path) -> None:
    """Place a completed staged file at ``final`` without reporting partial output as success.

    Same-filesystem placement uses ``os.replace`` directly. Cross-filesystem placement copies
    into a hidden partial file in the destination directory, atomically replaces the final path,
    then removes the staged file.
    """

    src = staged.resolve()
    dst = final
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
        return
    except OSError:
        pass

    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".partial", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        _best_effort_unlink(src)
    except Exception as exc:
        _best_effort_unlink(tmp)
        raise FileLifecycleError(f"Could not safely finalize {src} to {dst}: {exc}") from exc


def safe_unlink(path: Path, *, allowed_roots: Iterable[Path] | None = None) -> bool:
    """Delete one file. Missing files are treated as already absent.

    When ``allowed_roots`` is supplied, the target must normalize under one of
    those roots before deletion is attempted.
    """

    target = _authorized_path(path, allowed_roots=allowed_roots)
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise FileLifecycleError(f"Could not remove {path}: {exc}") from exc


def _authorized_path(path: Path, *, allowed_roots: Iterable[Path] | None) -> Path:
    if allowed_roots is None:
        return path

    target = os.path.abspath(os.fspath(path))
    for raw_root in allowed_roots:
        root = os.path.abspath(os.fspath(raw_root))
        try:
            if os.path.commonpath([target, root]) == root:
                return Path(target)
        except ValueError:
            continue
    raise FileLifecycleError("Refusing to remove a file outside the authorized folder roots.")


def _best_effort_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return
