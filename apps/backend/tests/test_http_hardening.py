from __future__ import annotations

import gzip
from dataclasses import replace
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.platform.http.compressed_assets import CompressedStaticAssetsMiddleware
from mediamop.platform.http.trusted_proxy import TrustedProxySchemeMiddleware


def test_trusted_proxy_applies_one_forwarded_scheme_only_for_trusted_peer() -> None:
    async def endpoint(request):
        return PlainTextResponse(request.url.scheme)

    settings = replace(MediaMopSettings.load(), trusted_proxy_ips=("127.0.0.1/32",))
    app = Starlette(routes=[Route("/", endpoint)])
    app.add_middleware(TrustedProxySchemeMiddleware, settings=settings)

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.get("/", headers={"X-Forwarded-Proto": "https"}).text == "https"
        assert client.get("/", headers={"X-Forwarded-Proto": "https, http"}).text == "http"


def test_compressed_assets_negotiate_and_cache(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    source = assets / "app-abc.js"
    source.write_text("console.log('source');", encoding="utf-8")
    (assets / "app-abc.js.br").write_bytes(b"brotli-bytes")
    (assets / "app-abc.js.gz").write_bytes(gzip.compress(b"gzip-bytes"))
    app = Starlette()
    app.mount("/", StaticFiles(directory=str(tmp_path)), name="static")
    app.add_middleware(CompressedStaticAssetsMiddleware, root=tmp_path)

    with TestClient(app) as client:
        br = client.get("/assets/app-abc.js", headers={"Accept-Encoding": "br, gzip"})
        assert br.status_code == 200
        assert br.content == b"brotli-bytes"
        assert br.headers["Content-Encoding"] == "br"
        assert br.headers["Cache-Control"] == "public, max-age=31536000, immutable"
        assert br.headers["Vary"] == "Accept-Encoding"
        assert br.headers["ETag"]

        gzip_response = client.get("/assets/app-abc.js", headers={"Accept-Encoding": "gzip"})
        assert gzip_response.status_code == 200
        assert gzip_response.content == b"gzip-bytes"
        assert gzip_response.headers["Content-Encoding"] == "gzip"

        unchanged = client.get(
            "/assets/app-abc.js",
            headers={"Accept-Encoding": "br", "If-None-Match": br.headers["ETag"]},
        )
        assert unchanged.status_code == 304
        assert unchanged.content == b""


def test_compressed_assets_do_not_intercept_range_requests(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app-abc.js").write_bytes(b"0123456789")
    (assets / "app-abc.js.gz").write_bytes(b"compressed")
    app = Starlette()
    app.mount("/", StaticFiles(directory=str(tmp_path)), name="static")
    app.add_middleware(CompressedStaticAssetsMiddleware, root=tmp_path)

    with TestClient(app) as client:
        response = client.get(
            "/assets/app-abc.js",
            headers={"Accept-Encoding": "gzip", "Range": "bytes=0-3"},
        )
        assert response.status_code == 206
        assert response.content == b"0123"
