"""Install fake ``ffprobe``/``ffmpeg`` executables into a folder Weir is pointed at.

Weir finds its tools through ``WEIR_FFMPEG_DIR`` (``resolve_ffprobe_ffmpeg``), which must hold
``ffprobe`` and ``ffmpeg`` — ``ffprobe.exe`` and ``ffmpeg.exe`` on Windows, and they must be real
executables there, because Weir runs them without a shell. A ``.cmd`` file renamed to ``.exe`` does
not start. So on Windows each tool is built the way pip builds console scripts: the ``distlib``
launcher that ships inside pip, followed by a shebang naming this interpreter and a zip holding
``fake_media_tool.py`` as ``__main__.py``. On Linux and macOS it is the script with a shebang.

Both variants run the same ``fake_media_tool.py``; see its docstring for ``script.json``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import platform
import shutil
import stat
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOL_SOURCE = Path(__file__).with_name("fake_media_tool.py")
MAGIC = b"FAKEMEDIA:"


def fake_media_bytes(probe: dict[str, Any], *, padding: int = 1024) -> bytes:
    """File content that the fake ffprobe reports as ``probe``. Padding gives it a plausible size."""

    return MAGIC + json.dumps(probe).encode("utf-8") + b" " * padding


def probe(
    *,
    video: int = 1,
    audio_languages: tuple[str, ...] = ("eng",),
    subtitle_languages: tuple[str, ...] = (),
    duration_seconds: float = 60.0,
) -> dict[str, Any]:
    """An ffprobe answer with the given tracks, indexed in order: video, audio, subtitles."""

    streams: list[dict[str, Any]] = []
    for _ in range(video):
        streams.append(
            {"index": len(streams), "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}
        )
    for lang in audio_languages:
        streams.append(
            {
                "index": len(streams),
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "tags": {"language": lang},
            }
        )
    for lang in subtitle_languages:
        streams.append(
            {"index": len(streams), "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": lang}}
        )
    return {"streams": streams, "format": {"duration": f"{duration_seconds:.1f}"}}


def _windows_launcher() -> bytes:
    spec = importlib.util.find_spec("pip")
    candidates: list[Path] = []
    if spec is not None and spec.origin:
        candidates.append(Path(spec.origin).parent / "_vendor" / "distlib")
    spec_distlib = importlib.util.find_spec("distlib")
    if spec_distlib is not None and spec_distlib.origin:
        candidates.append(Path(spec_distlib.origin).parent)
    name = "t64-arm.exe" if platform.machine().lower() in ("arm64", "aarch64") else "t64.exe"
    for folder in candidates:
        path = folder / name
        if path.is_file():
            return path.read_bytes()
    raise RuntimeError(
        "The fake ffmpeg needs pip's distlib launcher (pip/_vendor/distlib/t64.exe) to build a Windows executable."
    )


def _write_tool(path: Path) -> None:
    source = TOOL_SOURCE.read_bytes()
    interpreter = sys.executable
    if os.name == "nt":
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("__main__.py", source)
        quoted = f'"{interpreter}"' if " " in interpreter else interpreter
        path.write_bytes(_windows_launcher() + b"#!" + quoted.encode("utf-8") + b"\n" + archive.getvalue())
        return
    path.write_bytes(b"#!" + interpreter.encode("utf-8") + b"\n" + source)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@dataclass
class FakeFfmpeg:
    """A tool folder plus its script. Pass ``env`` to the server; edit ``script`` any time."""

    folder: Path

    @classmethod
    def install(cls, folder: Path) -> FakeFfmpeg:
        folder.mkdir(parents=True, exist_ok=True)
        suffix = ".exe" if os.name == "nt" else ""
        for tool in ("ffprobe", "ffmpeg"):
            _write_tool(folder / f"{tool}{suffix}")
        fake = cls(folder)
        fake.set_script({})
        return fake

    @property
    def env(self) -> dict[str, str]:
        return {"WEIR_FFMPEG_DIR": str(self.folder)}

    def set_script(self, script: dict[str, Any]) -> None:
        tmp = self.folder / "script.json.tmp"
        tmp.write_text(json.dumps(script), encoding="utf-8")
        tmp.replace(self.folder / "script.json")

    def set_file_rule(self, pattern: str, **rule: Any) -> None:
        script = json.loads((self.folder / "script.json").read_text(encoding="utf-8"))
        script.setdefault("files", {})[pattern] = rule
        self.set_script(script)

    def calls(self, *, tool: str | None = None, step: str | None = None) -> list[dict[str, Any]]:
        path = self.folder / "calls.jsonl"
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if tool is not None and entry.get("tool") != tool:
                continue
            if step is not None and entry.get("step") != step:
                continue
            out.append(entry)
        return out


def real_ffmpeg_dir() -> Path | None:
    """A folder holding real ffprobe and ffmpeg, or None. ``WEIR_CONTRACT_REAL_FFMPEG_DIR`` wins."""

    explicit = (os.environ.get("WEIR_CONTRACT_REAL_FFMPEG_DIR") or "").strip()
    if explicit:
        return Path(explicit) if Path(explicit).is_dir() else None
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return None
    folder = Path(ffmpeg).resolve().parent
    return folder if Path(ffprobe).resolve().parent == folder else None
