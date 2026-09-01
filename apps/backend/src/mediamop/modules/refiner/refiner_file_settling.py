"""Has this file finished being written, and can MediaMop actually touch it?

Refiner decided a file was finished by comparing its mtime against one global number.
That is a prediction — "writing usually takes less than N seconds" — and predictions fail
in both directions. Set it low and Refiner remuxes a half-written file. Set it high and
everything waits for a deadline that has nothing to do with the file. The case that
breaks it outright is a stalled download: mtime stops moving while the download is paused,
the threshold elapses, and the file looks finished precisely because nothing is happening
to it.

Watching the **size** asks the real question. Two observations of the same size, far
enough apart, is evidence that writing stopped. A resumed download changes the size and
starts the clock again on its own, with no special case for it.

The observations come from consecutive scans rather than from sleeping inside one. The
scan already runs on a cadence, the previous size is already a column, and a worker
blocked in ``sleep`` is a worker not doing anything else.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Self

from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow


@dataclass(frozen=True, slots=True)
class SettlingObservation:
    """What this scan saw, and what the next one needs to remember."""

    #: True while the size is still moving, or has not held still long enough yet.
    is_settling: bool
    #: Carried onto the file row so the next scan has something to compare against.
    size_changed_at: datetime | None
    #: When settling completes, if it is waiting on the clock rather than on the writer.
    stable_at: datetime | None
    reason: str | None = None


def observe_size_settling(
    *,
    library: RefinerLibraryRow,
    previous: RefinerFileRow | None,
    current_size_bytes: int,
    now: datetime | None = None,
) -> SettlingObservation:
    """Compare this scan's size against the last one.

    A file seen for the first time is treated as still settling: MediaMop has one
    observation and one observation cannot show that anything has stopped. It becomes
    stable once the interval passes with the size unchanged, which for the shipped
    defaults is one extra scan.
    """

    moment = now or datetime.now(UTC)
    interval = max(0, int(library.file_detection_interval_seconds))

    if library.ignore_size_changes or interval == 0:
        return SettlingObservation(is_settling=False, size_changed_at=moment, stable_at=moment)

    if previous is None:
        return SettlingObservation(
            is_settling=True,
            size_changed_at=moment,
            stable_at=moment + timedelta(seconds=interval),
            reason=("MediaMop has only just found this file and is checking whether anything is still writing to it."),
        )

    if int(previous.size_bytes) != int(current_size_bytes):
        return SettlingObservation(
            is_settling=True,
            size_changed_at=moment,
            stable_at=moment + timedelta(seconds=interval),
            reason=("This file is still growing, so something is writing to it. MediaMop will wait until it stops."),
        )

    # Same size. Without a recorded change moment there is nothing to measure the wait
    # against, so start it now rather than treating unknown as settled.
    changed_at = previous.size_changed_at
    if changed_at is None:
        return SettlingObservation(
            is_settling=True,
            size_changed_at=moment,
            stable_at=moment + timedelta(seconds=interval),
            reason="MediaMop is confirming that nothing is still writing to this file.",
        )

    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=UTC)
    stable_at = changed_at + timedelta(seconds=interval)
    if moment < stable_at:
        return SettlingObservation(
            is_settling=True,
            size_changed_at=changed_at,
            stable_at=stable_at,
            reason=(
                f"This file stopped changing very recently. MediaMop waits {interval}s to be sure nothing "
                "else is writing to it."
            ),
        )
    return SettlingObservation(is_settling=False, size_changed_at=changed_at, stable_at=stable_at)


@dataclass(frozen=True, slots=True)
class AccessCheck:
    """Whether MediaMop can read the source and write the destination."""

    ok: bool
    problem: str | None = None


class SourceReadGuard:
    """A held source handle that permits readers but prevents writers.

    Size and mtime checks cannot detect a preallocated download. On Windows, share-mode
    compatibility is the only reliable way to ask whether another process still owns
    write access. Keeping this handle open also prevents a writer from starting between
    preflight and ffmpeg.
    """

    __slots__ = ("_close", "_closed")

    def __init__(self, close: Callable[[], None]) -> None:
        self._close = close
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def acquire_source_read_guard(file_path: Path) -> tuple[SourceReadGuard | None, str | None]:
    """Reserve a source for read-only processing, or explain why Refiner must wait."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        generic_read = 0x80000000
        file_share_read = 0x00000001
        file_share_delete = 0x00000004
        open_existing = 3
        file_attribute_normal = 0x00000080
        invalid_handle_value = ctypes.c_void_p(-1).value
        handle = create_file(
            str(file_path),
            generic_read,
            file_share_read | file_share_delete,
            None,
            open_existing,
            file_attribute_normal,
            None,
        )
        if handle == invalid_handle_value:
            error = ctypes.get_last_error()
            if error in {32, 33}:
                return None, (
                    "This file is still open for writing by another program. MediaMop will wait until "
                    "the downloader or importer closes it."
                )
            return None, (
                "MediaMop could not reserve this file for safe read-only processing, so it will wait. "
                f"The system reported: {ctypes.WinError(error)}."
            )

        return SourceReadGuard(lambda: close_handle(handle)), None

    handle: BinaryIO | None = None
    try:
        handle = file_path.open("rb")
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except ImportError:
            pass
        except BlockingIOError:
            handle.close()
            return None, (
                "This file is still open for writing by another program. MediaMop will wait until "
                "the downloader or importer closes it."
            )
    except OSError as exc:
        if handle is not None:
            handle.close()
        return None, (
            "MediaMop could not reserve this file for safe read-only processing, so it will wait. "
            f"The system reported: {exc}."
        )
    return SourceReadGuard(handle.close), None


def source_writer_problem(file_path: Path) -> str | None:
    """Return an operator-readable wait reason when a source still has a writer."""

    guard, problem = acquire_source_read_guard(file_path)
    if guard is not None:
        guard.close()
    return problem


def _output_root_problem(output_folder: Path) -> str | None:
    probe = output_folder / f".mediamop-write-test-{os.getpid()}"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        with probe.open("wb") as handle:
            handle.write(b"0")
    except OSError as exc:
        return (
            f"MediaMop cannot write to the output folder ({output_folder}), so it did not start work that "
            f"would have nowhere to go. The system reported: {exc}."
        )
    finally:
        # A probe left behind is untidy, not a reason to hold the file: the write that
        # mattered already succeeded.
        with contextlib.suppress(OSError):
            probe.unlink()
    return None


def check_file_access(
    *,
    library: RefinerLibraryRow,
    file_path: Path,
    output_folder: Path | None,
) -> AccessCheck:
    """Confirm the source opens for reading and the output folder accepts a write.

    Run before queueing, because a file that cannot be opened is a *wait* at this point
    and a *failure* once a job exists for it. Windows and SMB shares both hold an
    exclusive lock while a download client writes, so this catches the common case that
    size settling alone would let through the moment the writer pauses.
    """

    if library.skip_access_tests:
        return AccessCheck(ok=True)

    try:
        with file_path.open("rb") as handle:
            handle.read(1)
    except OSError as exc:
        return AccessCheck(
            ok=False,
            problem=(
                "MediaMop could not open this file for reading — it is usually locked by whatever is still "
                f"writing it. The system reported: {exc}."
            ),
        )

    writer_problem = source_writer_problem(file_path)
    if writer_problem:
        return AccessCheck(ok=False, problem=writer_problem)

    if output_folder is not None:
        problem = _output_root_problem(output_folder)
        if problem:
            return AccessCheck(ok=False, problem=problem)

    return AccessCheck(ok=True)
