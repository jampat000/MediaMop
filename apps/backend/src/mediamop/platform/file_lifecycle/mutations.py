"""Recoverable file writes, moves, and deletes for media mutations."""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path


class FileLifecycleError(RuntimeError):
    """Raised when a guarded filesystem mutation cannot complete safely."""


def safe_copy_to_final(
    *,
    source: Path,
    final: Path,
    validate_staged: Callable[[Path], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """Copy ``source`` to ``final`` without exposing a partial destination file."""

    src = source.resolve()
    dst = final
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".partial", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if progress_callback is None:
            shutil.copy2(src, tmp)
        else:
            total_bytes = int(src.stat().st_size)
            copied_bytes = 0
            with src.open("rb") as source_handle, tmp.open("wb") as target_handle:
                while chunk := source_handle.read(8 * 1024 * 1024):
                    target_handle.write(chunk)
                    copied_bytes += len(chunk)
                    # Progress is optional observability. A dashboard update must
                    # never invalidate a safe copy that is otherwise succeeding.
                    with contextlib.suppress(Exception):
                        progress_callback(copied_bytes, total_bytes)
            shutil.copystat(src, tmp)
    except Exception as exc:
        _best_effort_unlink(tmp)
        raise FileLifecycleError(f"Could not safely copy {src} to {dst}: {exc}") from exc
    if validate_staged is not None:
        try:
            validate_staged(tmp)
        except Exception:
            _best_effort_unlink(tmp)
            raise
    try:
        os.replace(tmp, dst)
    except Exception as exc:
        _best_effort_unlink(tmp)
        raise FileLifecycleError(f"Could not safely publish the validated copy at {dst}: {exc}") from exc


def try_hardlink_to_final(
    *,
    source: Path,
    final: Path,
    validate_staged: Callable[[Path], None] | None = None,
) -> bool:
    """Validate and atomically expose a same-filesystem hardlink when supported.

    ``False`` means hardlink creation was rejected and the caller should use its
    copy fallback. Validation and publication errors remain failures: silently
    falling back after either one could hide an invalid output or overwrite decision.
    """

    src = source.resolve()
    dst = final
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".link", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    _best_effort_unlink(tmp)
    try:
        os.link(src, tmp)
    except OSError:
        _best_effort_unlink(tmp)
        return False
    try:
        if validate_staged is not None:
            validate_staged(tmp)
        os.replace(tmp, dst)
    except Exception:
        _best_effort_unlink(tmp)
        raise
    return True


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


def safe_unlink(path: Path) -> bool:
    """Delete one internally-owned file. Missing files are treated as already absent."""

    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise FileLifecycleError(f"Could not remove {path}: {exc}") from exc


def safe_unlink_under_roots(path: Path, *, allowed_roots: Sequence[Path]) -> bool:
    """Delete ``path`` only after it normalizes under one of ``allowed_roots``."""

    target = os.path.normpath(os.path.abspath(os.fspath(path)))
    for raw_root in allowed_roots:
        root = os.path.normpath(os.path.abspath(os.fspath(raw_root)))
        if target == root or target.startswith(root + os.sep):
            try:
                os.remove(target)
                return True
            except FileNotFoundError:
                return False
            except OSError as exc:
                raise FileLifecycleError(f"Could not remove {path}: {exc}") from exc
    raise FileLifecycleError("Refusing to remove a file outside the authorized folder roots.")


def _best_effort_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        return
