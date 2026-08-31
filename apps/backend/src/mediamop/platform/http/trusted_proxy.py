"""Apply forwarded request scheme only when the immediate peer is trusted.

The packaged server normally sits behind a local reverse proxy.  Trusting every
``X-Forwarded-Proto`` header would let a client spoof HTTPS and weaken origin and
cookie decisions, so the header is considered only when the socket peer belongs
to an explicitly configured ``MEDIAMOP_TRUSTED_PROXY_IPS`` network.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from mediamop.core.config import MediaMopSettings


def _networks(values: Iterable[str]) -> tuple[ipaddress._BaseNetwork, ...]:
    parsed: list[ipaddress._BaseNetwork] = []
    for value in values:
        try:
            parsed.append(ipaddress.ip_network(str(value).strip(), strict=False))
        except ValueError:
            continue
    return tuple(parsed)


def _peer_is_trusted(peer: str | None, values: Iterable[str]) -> bool:
    if not peer:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in _networks(values))


class TrustedProxySchemeMiddleware:
    """Rewrite only the ASGI scheme supplied by a configured reverse proxy."""

    def __init__(self, app, *, settings: MediaMopSettings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        peer = (scope.get("client") or (None,))[0]
        if not _peer_is_trusted(peer, self.settings.trusted_proxy_ips):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_scheme = headers.get(b"x-forwarded-proto", b"").decode("latin-1").strip().lower()
        # A proxy must send one unambiguous protocol.  Comma-separated chains are
        # deliberately rejected because this middleware does not know which hop is ours.
        if raw_scheme in {"http", "https"}:
            scope = dict(scope)
            scope["scheme"] = raw_scheme
        await self.app(scope, receive, send)
