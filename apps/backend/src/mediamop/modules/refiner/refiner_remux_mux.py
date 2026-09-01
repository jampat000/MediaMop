"""FFprobe / FFmpeg remux execution — Refiner-owned.

Binary resolution: ``<MEDIAMOP_HOME>/bin/ffmpeg/{ffprobe,ffmpeg}[.exe]`` first, then ``PATH``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mediamop.modules.refiner.refiner_metadata_rules import metadata_argv_flags
from mediamop.modules.refiner.refiner_remux_rules import RemuxPlan

logger = logging.getLogger(__name__)

REFINER_FFMPEG_TIMEOUT_S: int = 3600
REFINER_FFMPEG_SLOW_GRACE_S: int = 60
REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S: int = 12 * 60 * 60
_REFINER_FFPROBE_LOG_MAX_CHARS = 2000
_REFINER_FFMPEG_STDERR_TAIL_BYTES = 32 * 1024


class MediaCompletenessError(RuntimeError):
    """A staged or source media file cannot be trusted as complete."""


def _clip_probe_text(raw: object, *, max_chars: int = _REFINER_FFPROBE_LOG_MAX_CHARS) -> str:
    t = "" if raw is None else str(raw)
    if len(t) > max_chars:
        return t[:max_chars] + "…(truncated)"
    return t


def _read_tail_text(path: Path, *, max_bytes: int = _REFINER_FFMPEG_STDERR_TAIL_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            return handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def resolve_ffprobe_ffmpeg(*, mediamop_home: str) -> tuple[str, str]:
    """Prefer bundled tools under ``mediamop_home``, then host ``PATH``."""

    home = Path(mediamop_home).expanduser().resolve()
    candidate_dirs: list[Path] = []
    raw_env_dir = (os.environ.get("MEDIAMOP_FFMPEG_DIR") or "").strip()
    if raw_env_dir:
        candidate_dirs.append(Path(raw_env_dir).expanduser())
    candidate_dirs.append(home / "bin" / "ffmpeg")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidate_dirs.extend(
            [
                exe_dir / "bin" / "ffmpeg",
                exe_dir / "_internal" / "bin" / "ffmpeg",
            ]
        )

    names = ("ffprobe.exe", "ffmpeg.exe") if os.name == "nt" else ("ffprobe", "ffmpeg")
    for candidate_dir in candidate_dirs:
        ffprobe_path = candidate_dir / names[0]
        ffmpeg_path = candidate_dir / names[1]
        if ffprobe_path.is_file() and ffmpeg_path.is_file():
            return str(ffprobe_path), str(ffmpeg_path)

    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise RuntimeError(
            "Refiner could not find the video tools it needs. Windows and Docker installs should include them; "
            "source installs must provide ffprobe and ffmpeg on PATH or set MEDIAMOP_FFMPEG_DIR.",
        )
    return ffprobe, ffmpeg


def build_ffprobe_argv(
    *,
    ffprobe_bin: str,
    src: Path,
    probe_size_mb: int = 10,
    analyze_duration_seconds: int = 10,
) -> list[str]:
    """Build ffprobe args for Refiner preflight probe."""
    ps_mb = max(1, min(1024, int(probe_size_mb)))
    ad_s = max(1, min(300, int(analyze_duration_seconds)))
    return [
        ffprobe_bin,
        "-v",
        "quiet",
        "-probesize",
        str(ps_mb * 1024 * 1024),
        "-analyzeduration",
        str(ad_s * 1_000_000),
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(src),
    ]


def ffprobe_json(
    path: Path,
    *,
    mediamop_home: str,
    timeout_s: int = 120,
    probe_size_mb: int = 10,
    analyze_duration_seconds: int = 10,
) -> dict[str, Any]:
    ffprobe, _ = resolve_ffprobe_ffmpeg(mediamop_home=mediamop_home)
    try:
        resolved_path = str(path.resolve())
    except OSError:
        resolved_path = str(path)
    exists = bool(path.exists())
    is_file = bool(path.is_file())
    try:
        st = path.stat()
        f_size = int(st.st_size)
        f_mtime = float(st.st_mtime)
    except OSError:
        f_size = -1
        f_mtime = 0.0
    logger.debug(
        "REFINER_FFPROBE_FILE_STATE: %s",
        json.dumps(
            {
                "path": str(path),
                "resolved_path": resolved_path,
                "exists": exists,
                "is_file": is_file,
                "size_bytes": f_size,
                "suffix": _clip_probe_text(path.suffix, max_chars=64),
                "mtime_epoch": f_mtime,
            },
            ensure_ascii=True,
        ),
    )
    if (not exists) or (not is_file) or f_size == 0:
        raise RuntimeError("file missing or empty at probe time")
    argv = build_ffprobe_argv(
        ffprobe_bin=ffprobe,
        src=path,
        probe_size_mb=probe_size_mb,
        analyze_duration_seconds=analyze_duration_seconds,
    )
    logger.debug(
        "REFINER_FFPROBE_CALL: %s",
        json.dumps(
            {
                "path": str(path),
                "argv": [_clip_probe_text(a, max_chars=256) for a in argv],
            },
            ensure_ascii=True,
        ),
    )
    r = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    log = logger.warning if r.returncode != 0 else logger.debug
    log(
        "REFINER_FFPROBE_RESULT: %s",
        json.dumps(
            {
                "path": str(path),
                "returncode": int(getattr(r, "returncode", -1)),
                "stdout": _clip_probe_text(getattr(r, "stdout", "")),
                "stderr": _clip_probe_text(getattr(r, "stderr", "")),
            },
            ensure_ascii=True,
        ),
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "").strip() or "ffprobe failed")
    raw = r.stdout
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError("ffprobe returned invalid or empty output")
    try:
        parsed = json.loads(raw)
    except Exception as e:
        raise RuntimeError("ffprobe returned invalid or empty output") from e
    if not isinstance(parsed, dict):
        raise RuntimeError("ffprobe returned invalid or empty output")
    return parsed


def _probe_duration_seconds(data: dict[str, Any]) -> float | None:
    candidates: list[float] = []
    fmt = data.get("format")
    if isinstance(fmt, dict):
        with contextlib.suppress(TypeError, ValueError):
            candidates.append(float(fmt.get("duration") or 0))
    streams = data.get("streams")
    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            with contextlib.suppress(TypeError, ValueError):
                candidates.append(float(stream.get("duration") or 0))
    valid = [duration for duration in candidates if duration > 0]
    return max(valid) if valid else None


def validate_remux_output(
    path: Path,
    *,
    mediamop_home: str,
    expected_audio: int = 0,
    expected_duration_seconds: float | None = None,
) -> None:
    data = ffprobe_json(path, mediamop_home=mediamop_home)
    streams = data.get("streams") or []
    if not isinstance(streams, list):
        raise RuntimeError("validation failed: invalid ffprobe output")
    n_audio = 0
    for s in streams:
        if isinstance(s, dict) and (s.get("codec_type") or "").lower() == "audio":
            n_audio += 1
    if n_audio < 1:
        raise RuntimeError("validation failed: output has no audio stream")
    if expected_audio > 0 and n_audio != expected_audio:
        raise RuntimeError(
            f"validation failed: expected {expected_audio} audio stream(s), got {n_audio}",
        )
    if expected_duration_seconds is not None and expected_duration_seconds > 0:
        output_duration = _probe_duration_seconds(data)
        if output_duration is None:
            raise MediaCompletenessError(
                "Validation failed: Refiner could not confirm the staged output duration, so it was not published."
            )
        tolerance = max(5.0, expected_duration_seconds * 0.01)
        if output_duration < expected_duration_seconds - tolerance:
            raise MediaCompletenessError(
                "Validation failed: the staged output is incomplete "
                f"({output_duration:.1f}s of {expected_duration_seconds:.1f}s expected), so it was not published."
            )


def validate_media_integrity(path: Path, *, mediamop_home: str) -> None:
    """Read the primary video from start to finish and fail on damaged/truncated input.

    Docker bind mounts cannot always expose another process's write handle. A complete
    demux pass is therefore the authoritative preflight there: it catches sparse or
    preallocated downloads whose logical size and metadata already look final.
    """

    _, ffmpeg_bin = resolve_ffprobe_ffmpeg(mediamop_home=mediamop_home)
    argv = [
        ffmpeg_bin,
        "-hide_banner",
        "-v",
        "error",
        "-xerror",
        "-err_detect",
        "explode",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=REFINER_FFMPEG_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        if len(detail) > _REFINER_FFPROBE_LOG_MAX_CHARS:
            detail = detail[:_REFINER_FFPROBE_LOG_MAX_CHARS] + "…(truncated)"
        raise MediaCompletenessError(
            "MediaMop could not read this media file from start to finish. It may still be downloading or may be "
            f"incomplete, so Refiner will wait. The media check reported: {detail or 'incomplete media data'}."
        )


def build_ffmpeg_argv(
    *,
    ffmpeg_bin: str,
    src: Path,
    dst: Path,
    plan: RemuxPlan,
    input_flags: list[str] | None = None,
) -> list[str]:
    # ``input_flags`` carries hardware acceleration and strictness. They go *before* -i,
    # because -hwaccel applies to the input that follows it; after -i they are silently
    # ignored, which is the failure mode where nothing looks wrong and nothing is faster.
    args = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-xerror",
        "-err_detect",
        "explode",
        "-nostdin",
        "-y",
    ]
    args.extend(input_flags or [])
    args.extend(["-i", str(src)])
    for vi in plan.video_indices:
        args.extend(["-map", f"0:{vi}"])
    for t in plan.audio:
        args.extend(["-map", f"0:{t.input_index}"])
    for t in plan.subtitles:
        args.extend(["-map", f"0:{t.input_index}"])
    args.extend(["-c", "copy"])
    # Container-level stripping. After the maps, because the maps decide which streams
    # exist and these decide what those streams carry.
    args.extend(metadata_argv_flags(plan.metadata))
    for i, t in enumerate(plan.audio):
        args.extend([f"-disposition:a:{i:d}", "default" if t.default else "0"])
    for i, t in enumerate(plan.subtitles):
        flags: list[str] = []
        if t.default:
            flags.append("default")
        if t.forced:
            flags.append("forced")
        args.extend([f"-disposition:s:{i:d}", "+".join(flags) if flags else "0"])
    args.append(str(dst))
    return args


def _argv_with_progress(argv: list[str]) -> list[str]:
    out = list(argv)
    insert_at = len(out) - 1 if len(out) > 1 else len(out)
    return out[:insert_at] + ["-progress", "pipe:1", "-nostats"] + out[insert_at:]


def run_ffmpeg(
    argv: list[str],
    *,
    timeout_s: int | None = REFINER_FFMPEG_TIMEOUT_S,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    duration_seconds: float | None = None,
) -> None:
    if progress_callback is None:
        with tempfile.NamedTemporaryFile(delete=False) as stderr_file:
            stderr_path = Path(stderr_file.name)
        try:
            with stderr_path.open("wb") as stderr_handle:
                r = subprocess.run(
                    argv,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_handle,
                    stdin=subprocess.DEVNULL,
                    timeout=timeout_s,
                    check=False,
                )
            if r.returncode != 0:
                msg = _read_tail_text(stderr_path)
                raise RuntimeError(msg or "ffmpeg failed")
        finally:
            try:
                stderr_path.unlink(missing_ok=True)
            except OSError:
                logger.debug(
                    "Refiner: could not remove temporary ffmpeg stderr log %s",
                    stderr_path,
                    exc_info=True,
                )
        return

    progress_argv = _argv_with_progress(argv)
    started = time.monotonic()
    fields: dict[str, str] = {}
    with tempfile.NamedTemporaryFile(delete=False) as stderr_file:
        stderr_path = Path(stderr_file.name)
    try:
        with stderr_path.open("wb") as stderr_handle:
            proc = subprocess.Popen(
                progress_argv,
                stdout=subprocess.PIPE,
                stderr=stderr_handle,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.stdout is None:
                proc.kill()
                raise RuntimeError("ffmpeg progress stream is unavailable")
            try:
                for raw in proc.stdout:
                    elapsed = max(0.0, time.monotonic() - started)
                    if timeout_s is not None and elapsed > timeout_s:
                        proc.kill()
                        raise RuntimeError("ffmpeg timed out")
                    line = raw.strip()
                    if not line or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    fields[key] = value
                    if key != "progress":
                        continue
                    out_time_s: float | None = None
                    try:
                        out_time_s = max(0.0, float(fields.get("out_time_ms", "0")) / 1_000_000.0)
                    except ValueError:
                        out_time_s = None
                    percent: float | None = None
                    eta_s: int | None = None
                    if duration_seconds and duration_seconds > 0 and out_time_s is not None:
                        percent = max(
                            0.0,
                            min(99.0 if value != "end" else 100.0, (out_time_s / duration_seconds) * 100.0),
                        )
                        if percent > 0 and value != "end":
                            total_est = elapsed / (percent / 100.0)
                            eta_s = max(0, int(total_est - elapsed))
                    if value == "end":
                        percent = 100.0
                        eta_s = 0
                    if (
                        elapsed >= REFINER_FFMPEG_SLOW_GRACE_S
                        and eta_s is not None
                        and eta_s > REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S
                    ):
                        proc.kill()
                        raise RuntimeError(
                            "ffmpeg was stopped because progress projected more than 12 hours remaining. "
                            "The input may be malformed, mislabeled, or unreadable at a usable speed."
                        )
                    progress_callback(
                        {
                            "percent": percent,
                            "eta_seconds": eta_s,
                            "elapsed_seconds": int(elapsed),
                            "processed_seconds": out_time_s,
                            "speed": fields.get("speed"),
                            "progress": value,
                        }
                    )
                rc = proc.wait(timeout=5)
            except Exception:
                if proc.poll() is None:
                    proc.kill()
                raise
        if rc != 0:
            raise RuntimeError(_read_tail_text(stderr_path) or "ffmpeg failed")
    finally:
        try:
            stderr_path.unlink(missing_ok=True)
        except OSError:
            logger.debug(
                "Refiner: could not remove temporary ffmpeg stderr log %s",
                stderr_path,
                exc_info=True,
            )


def remux_to_temp_file(
    *,
    src: Path,
    work_dir: Path,
    plan: RemuxPlan,
    mediamop_home: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    duration_seconds: float | None = None,
) -> Path:
    """Write remux output into work_dir and validate it. Caller owns move/delete decisions."""

    _, ffmpeg_bin = resolve_ffprobe_ffmpeg(mediamop_home=mediamop_home)
    work_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        suffix=src.suffix or ".mkv",
        prefix=f"{src.stem}.refiner.",
        dir=str(work_dir),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        argv = build_ffmpeg_argv(ffmpeg_bin=ffmpeg_bin, src=src, dst=tmp_path, plan=plan)
        logger.debug("Refiner: ffmpeg %s", " ".join(argv[:8]) + " ...")
        run_ffmpeg(argv, progress_callback=progress_callback, duration_seconds=duration_seconds)
        validate_remux_output(
            tmp_path,
            mediamop_home=mediamop_home,
            expected_audio=len(plan.audio),
            expected_duration_seconds=duration_seconds,
        )
    except Exception:
        try:
            if tmp_path.is_file():
                tmp_path.unlink()
        except OSError:
            logger.warning("Refiner: could not remove temp file %s", tmp_path, exc_info=True)
        raise
    return tmp_path
