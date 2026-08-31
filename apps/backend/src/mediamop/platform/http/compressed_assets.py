"""Serve hashed SPA assets with negotiated compression and immutable caching."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path, PurePosixPath

from starlette.responses import FileResponse, Response

_COMPRESSIBLE_SUFFIXES = frozenset({".css", ".html", ".js", ".json", ".map", ".svg", ".txt", ".wasm", ".xml"})
_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _asset_path(root: Path, url_path: str) -> Path | None:
    if not url_path.startswith("/assets/"):
        return None
    relative = PurePosixPath(url_path.removeprefix("/"))
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    candidate = (root / Path(*relative.parts)).resolve()
    assets_root = (root / "assets").resolve()
    try:
        candidate.relative_to(assets_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _accepts_encoding(raw: str, encoding: str) -> bool:
    wildcard = False
    for item in raw.lower().split(","):
        name, _, options = item.strip().partition(";")
        q = 1.0
        for option in options.split(";"):
            key, _, value = option.strip().partition("=")
            if key == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        if name == encoding:
            return q > 0
        if name == "*":
            wildcard = q > 0
    return wildcard


def _etag(path: Path, *, encoding: str | None) -> str:
    stat = path.stat()
    suffix = f"-{encoding}" if encoding else ""
    material = f"{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}{suffix}".encode("ascii")
    return f'"{hashlib.sha256(material).hexdigest()[:24]}"'


def _asset_headers(path: Path, *, encoding: str | None, etag: str) -> dict[str, str]:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {
        "Cache-Control": _CACHE_CONTROL,
        "ETag": etag,
        "Vary": "Accept-Encoding",
        "Content-Type": media_type,
    }
    if encoding:
        headers["Content-Encoding"] = encoding
    return headers


class CompressedStaticAssetsMiddleware:
    """Intercept only safe ``/assets`` files; API and HTML stay non-cacheable."""

    def __init__(self, app, *, root: Path) -> None:
        self.app = app
        self.root = root

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return

        # Range requests must retain StaticFiles' range semantics.  A compressed
        # representation cannot safely answer a byte range for the source file.
        header_map = {key.lower(): value for key, value in scope.get("headers", [])}
        if b"range" in header_map:
            await self.app(scope, receive, send)
            return

        path = _asset_path(self.root, scope.get("path", ""))
        if path is None:
            await self.app(scope, receive, send)
            return

        encoding: str | None = None
        served = path
        if path.suffix.lower() in _COMPRESSIBLE_SUFFIXES:
            accept = header_map.get(b"accept-encoding", b"").decode("latin-1")
            for candidate in ("br", "gzip"):
                suffix = "gz" if candidate == "gzip" else candidate
                compressed = Path(f"{path}.{suffix}")
                if _accepts_encoding(accept, candidate) and compressed.is_file():
                    served = compressed
                    encoding = candidate
                    break

        etag = _etag(served, encoding=encoding)
        headers = _asset_headers(path, encoding=encoding, etag=etag)
        if header_map.get(b"if-none-match", b"").decode("latin-1").strip() == etag:
            await Response(status_code=304, headers=headers)(scope, receive, send)
            return

        response = FileResponse(
            served,
            media_type=headers.pop("Content-Type"),
            headers=headers,
        )
        await response(scope, receive, send)
