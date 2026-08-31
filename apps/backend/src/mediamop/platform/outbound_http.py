"""Shared outbound HTTP URL policy helpers used by Pruner/Refiner and ARR clients.

Configuration-time validation is intentionally cheap.  Callers that make an outbound
request must use :func:`post_json_to_external_url`, which resolves and validates the
destination immediately before opening the socket and then connects to that exact
address.  That distinction closes the DNS-rebinding window between saving a URL and
using it.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


def normalize_local_service_base_url(raw: str) -> str:
    """Normalize base URL for locally configured services (Arr, Plex, Jellyfin, Emby)."""

    parsed = urlsplit(raw.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be a valid http(s) URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL must not include credentials, query strings, or fragments.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_external_provider_url(raw: str) -> str:
    """Validate provider URLs that must never target localhost/private addresses."""

    parsed = urlsplit(raw.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Blocked provider URL scheme: {parsed.scheme or '<missing>'}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("Blocked provider URL host: <missing>")
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        raise ValueError(f"Blocked provider URL host: {host}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return raw
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise ValueError(f"Blocked provider URL host: {host}")
    return raw


class ExternalEndpointError(ValueError):
    """A safe, operator-facing error for a rejected or unreachable external endpoint."""


@dataclass(frozen=True, slots=True)
class ResolvedExternalEndpoint:
    scheme: str
    hostname: str
    port: int
    address: str
    request_target: str


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    # ``is_global`` is false for private, loopback, link-local, multicast,
    # reserved, unspecified, documentation and otherwise non-routable ranges.
    return bool(ip.is_global)


def resolve_public_external_endpoint(raw: str) -> ResolvedExternalEndpoint:
    """Parse, resolve and validate one external URL immediately before connecting.

    Every address returned by DNS must be public.  Accepting one public answer while
    silently ignoring a private answer lets a resolver choose the private answer on a
    later connection, so mixed public/private results are rejected as a whole.
    """

    parsed = urlsplit((raw or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ExternalEndpointError("The notification destination must be a valid external HTTP(S) address.")
    if parsed.username or parsed.password:
        raise ExternalEndpointError("The notification destination must not contain embedded credentials.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ExternalEndpointError("The notification destination has an invalid port.") from exc
    hostname = parsed.hostname
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ExternalEndpointError("MediaMop could not resolve the notification destination.") from exc
    addresses: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in infos:
        address = str(sockaddr[0])
        if address not in addresses:
            addresses.append(address)
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ExternalEndpointError("The notification destination resolved to a non-public network address.")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return ResolvedExternalEndpoint(
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        address=addresses[0],
        request_target=path,
    )


def post_json_to_external_url(
    raw_url: str,
    *,
    body: bytes,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> int:
    """POST JSON to a validated public endpoint without following redirects.

    The socket is opened against the address just validated.  HTTPS still uses the
    configured hostname for certificate verification and SNI, while the HTTP Host
    header remains the hostname rather than the pinned IP.
    """

    endpoint = resolve_public_external_endpoint(raw_url)
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request_headers.setdefault("Content-Length", str(len(body)))
    sock: socket.socket | ssl.SSLSocket | None = None
    connection: http.client.HTTPConnection | http.client.HTTPSConnection | None = None
    try:
        try:
            sock = socket.create_connection((endpoint.address, endpoint.port), timeout=timeout)
        except OSError as exc:
            raise ExternalEndpointError("MediaMop could not connect to the notification destination.") from exc

        if endpoint.scheme == "https":
            context = _secure_external_tls_context()
            try:
                sock = context.wrap_socket(sock, server_hostname=endpoint.hostname)
            except (OSError, ssl.SSLError) as exc:
                raise ExternalEndpointError("MediaMop could not establish secure notification delivery.") from exc
            connection = http.client.HTTPSConnection(endpoint.hostname, endpoint.port, timeout=timeout)
        else:
            connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=timeout)
        # Assign the already-connected socket so HTTPConnection.connect() cannot
        # perform a second DNS lookup after the validation above.
        connection.sock = sock
        connection.request("POST", endpoint.request_target, body=body, headers=request_headers)
        response = connection.getresponse()
        response.read(64 * 1024)
        if 300 <= response.status < 400:
            raise ExternalEndpointError("The notification destination returned a redirect; redirects are disabled.")
        return int(response.status)
    except ExternalEndpointError:
        raise
    except (OSError, http.client.HTTPException, TimeoutError) as exc:
        raise ExternalEndpointError("MediaMop could not deliver the notification.") from exc
    finally:
        if connection is not None:
            with suppress(OSError):
                connection.close()
        elif sock is not None:
            with suppress(OSError):
                sock.close()


def safe_external_error_message(exc: BaseException) -> str:
    """Return a stable error without URLs, response bodies or exception internals."""

    if isinstance(exc, ExternalEndpointError):
        return str(exc)
    return "MediaMop could not deliver the notification. Check the destination and server logs."


def _secure_external_tls_context() -> ssl.SSLContext:
    """Build the minimum TLS policy used for outbound provider connections."""

    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
