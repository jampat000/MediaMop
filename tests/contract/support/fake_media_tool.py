"""A stand-in for ``ffprobe`` and ``ffmpeg``. Standard library only; run as its own process.

It is installed twice into one folder (see ``fake_ffmpeg.py``), and knows which tool it is by its
own file name. Behaviour comes from ``script.json`` beside it, so a test decides what each input
"contains" and how each step ends, and every call is appended to ``calls.jsonl`` for assertions.

Media files
    A file whose bytes start with ``FAKEMEDIA:`` carries its own ffprobe JSON after the prefix
    (see ``fake_media_bytes``). Any other file is described by the first ``files`` rule whose glob
    matches its base name, or by ``default``.

``script.json``::

    {"files": {"*.mkv": {"probe": {...},            # ffprobe JSON (else the embedded/default one)
                         "probe_error": "text",     # ffprobe exits 1 with this on stderr
                         "integrity_error": "text", # the ffmpeg -f null read-through fails
                         "remux_error": "text",     # the remux fails ...
                         "remux_fail_times": 2,     # ... only for the first N remuxes of that name
                         "remux_delay_seconds": 5}},# the remux takes this long (writes a partial file first)
     "default": {...}}

A remux writes ``FAKEMEDIA:`` plus the source's probe restricted to the ``-map``-ed streams, so the
output validates exactly as the plan says it should.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
import time
from pathlib import Path

MAGIC = b"FAKEMEDIA:"


def _tool_dir() -> Path:
    override = os.environ.get("WEIR_CONTRACT_FAKE_TOOL_DIR")
    if override:
        return Path(override)
    return Path(sys.argv[0]).resolve().parent


def _load_script(tool_dir: Path) -> dict:
    try:
        return json.loads((tool_dir / "script.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _rule_for(script: dict, path: str) -> dict:
    name = os.path.basename(path)
    for pattern, rule in (script.get("files") or {}).items():
        if fnmatch.fnmatch(name, pattern):
            return rule or {}
    return script.get("default") or {}


def _log(tool_dir: Path, tool: str, argv: list[str], **extra: object) -> None:
    line = json.dumps({"tool": tool, "argv": argv, "at": time.time(), **extra})
    with open(tool_dir / "calls.jsonl", "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _bump_counter(tool_dir: Path, key: str) -> int:
    """How many times ``key`` has been seen, including this time. Serialised with a lock file."""

    lock = tool_dir / "counters.lock"
    deadline = time.time() + 10
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() > deadline:
                lock.unlink(missing_ok=True)
            time.sleep(0.01)
    try:
        path = tool_dir / "counters.json"
        try:
            counters = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            counters = {}
        counters[key] = int(counters.get(key, 0)) + 1
        path.write_text(json.dumps(counters), encoding="utf-8")
        return int(counters[key])
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


DEFAULT_PROBE = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
        {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}},
    ],
    "format": {"duration": "60.0"},
}


def _probe_for(script: dict, path: str) -> dict:
    try:
        with open(path, "rb") as handle:
            head = handle.read(len(MAGIC))
            if head == MAGIC:
                return json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError):
        pass
    rule = _rule_for(script, path)
    probe = rule.get("probe")
    return probe if isinstance(probe, dict) else DEFAULT_PROBE


def _ffprobe(tool_dir: Path, script: dict, argv: list[str]) -> int:
    path = argv[-1] if argv else ""
    _log(tool_dir, "ffprobe", argv, file=os.path.basename(path))
    rule = _rule_for(script, path)
    if not os.path.isfile(path):
        sys.stderr.write(f"{path}: No such file or directory\n")
        return 1
    if rule.get("probe_error") and not _is_fake_output(path):
        sys.stderr.write(str(rule["probe_error"]) + "\n")
        return 1
    sys.stdout.write(json.dumps(_probe_for(script, path)))
    return 0


def _is_fake_output(path: str) -> bool:
    return ".refiner." in os.path.basename(path)


def _arg_after(argv: list[str], flag: str) -> str | None:
    for i, value in enumerate(argv[:-1]):
        if value == flag:
            return argv[i + 1]
    return None


def _ffmpeg(tool_dir: Path, script: dict, argv: list[str]) -> int:
    source = _arg_after(argv, "-i")
    if source is None:
        _log(tool_dir, "ffmpeg", argv, step="query")
        if "-hwaccels" in argv:
            sys.stdout.write("Hardware acceleration methods:\n\n")
        return 0
    rule = _rule_for(script, source)
    name = os.path.basename(source)
    if "null" in argv and _arg_after(argv, "-f") == "null":
        _log(tool_dir, "ffmpeg", argv, step="integrity", file=name)
        if rule.get("integrity_error"):
            sys.stderr.write(str(rule["integrity_error"]) + "\n")
            return 1
        return 0

    attempt = _bump_counter(tool_dir, f"remux:{name}")
    _log(tool_dir, "ffmpeg", argv, step="remux", file=name, attempt=attempt)
    output = argv[-1]
    delay = float(rule.get("remux_delay_seconds") or 0)
    if delay > 0:
        with open(output, "wb") as handle:
            handle.write(b"partial fake output")
        time.sleep(delay)
    error = rule.get("remux_error")
    fail_times = rule.get("remux_fail_times")
    if error and (fail_times is None or attempt <= int(fail_times)):
        sys.stderr.write(str(error) + "\n")
        return 1

    probe = _probe_for(script, source)
    by_index = {int(s.get("index", i)): s for i, s in enumerate(probe.get("streams") or [])}
    mapped = []
    for i, value in enumerate(argv[:-1]):
        if value == "-map" and argv[i + 1].startswith("0:"):
            try:
                mapped.append(int(argv[i + 1].split(":", 1)[1]))
            except ValueError:
                continue
    streams = []
    for new_index, old_index in enumerate(mapped):
        stream = dict(by_index.get(old_index) or {})
        if stream:
            stream["index"] = new_index
            streams.append(stream)
    out_probe = rule.get("output_probe") if isinstance(rule.get("output_probe"), dict) else None
    body = out_probe or {"streams": streams, "format": dict(probe.get("format") or {})}
    with open(output, "wb") as handle:
        handle.write(MAGIC + json.dumps(body).encode("utf-8"))
    if "-progress" in argv:
        sys.stdout.write("out_time_ms=0\nprogress=continue\nprogress=end\n")
    return 0


def main() -> int:
    tool_dir = _tool_dir()
    script = _load_script(tool_dir)
    tool = os.path.basename(sys.argv[0]).lower()
    argv = sys.argv[1:]
    if tool.startswith("ffprobe"):
        return _ffprobe(tool_dir, script, argv)
    return _ffmpeg(tool_dir, script, argv)


if __name__ == "__main__":
    raise SystemExit(main())
