"""Contract port of apps/backend/tests/test_http_hardening.py.

The original drives the trusted-proxy and compressed-asset middlewares on bare Starlette apps; here
the same behaviour is observed on a real server: the forwarded scheme through the sign-in cookie's
``Secure`` flag, and the assets through a ``WEIR_WEB_DIST`` folder with pre-compressed siblings.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from tests.contract.auth import _helpers as h
from tests.contract.support.client import WeirClient


@pytest.fixture(scope="module")
def web_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    dist = h.write_web_dist(tmp_path_factory.mktemp("web") / "dist")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app-abc.js").write_text("console.log('source');", encoding="utf-8")
    (assets / "app-abc.js.br").write_bytes(b"brotli-bytes")
    (assets / "app-abc.js.gz").write_bytes(gzip.compress(b"gzip-bytes"))
    (assets / "range-abc.js").write_bytes(b"0123456789")
    (assets / "range-abc.js.gz").write_bytes(b"compressed")
    return dist


@pytest.fixture(scope="module")
def server_env(web_dist: Path) -> dict[str, str]:
    return {"WEIR_TRUSTED_PROXY_IPS": "127.0.0.1/32", "WEIR_WEB_DIST": str(web_dist)}


def test_trusted_proxy_applies_one_forwarded_scheme_only_for_trusted_peer(client: WeirClient) -> None:
    h.ensure_admin_account(client)

    https = h.post_login(client, headers={"X-Forwarded-Proto": "https"})
    assert https.status_code == 200, https.text
    assert "secure" in h.set_cookie_header(https).lower()

    # A chain is ambiguous (which hop is ours?), so the request stays plain HTTP.
    chain = h.post_login(client, headers={"X-Forwarded-Proto": "https, http"})
    assert chain.status_code == 200, chain.text
    assert "secure" not in h.set_cookie_header(chain).lower()


def test_compressed_assets_negotiate_and_cache(client: WeirClient) -> None:
    # The .br sibling holds fake bytes a brotli decoder would reject, so read the body undecoded.
    with client.http.stream("GET", "/assets/app-abc.js", headers={"Accept-Encoding": "br, gzip"}) as br:
        assert br.status_code == 200
        assert b"".join(br.iter_raw()) == b"brotli-bytes"
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


def test_compressed_assets_do_not_intercept_range_requests(client: WeirClient) -> None:
    response = client.get("/assets/range-abc.js", headers={"Accept-Encoding": "gzip", "Range": "bytes=0-3"})
    assert response.status_code == 206
    assert response.content == b"0123"
