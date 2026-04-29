from types import SimpleNamespace

from mediamop.platform.auth.rate_limit import client_rate_limit_key


def _request(*, peer: str, xff: str = "", trusted_proxy_ips: tuple[str, ...] = ()):
    return SimpleNamespace(
        client=SimpleNamespace(host=peer),
        headers={"x-forwarded-for": xff} if xff else {},
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(trusted_proxy_ips=trusted_proxy_ips))),
    )


def test_rate_limit_ignores_forwarded_for_without_trusted_proxy() -> None:
    request = _request(peer="172.18.0.2", xff="203.0.113.10")
    assert client_rate_limit_key(request) == "172.18.0.2"


def test_rate_limit_ignores_forwarded_for_from_untrusted_peer() -> None:
    request = _request(peer="172.18.0.2", xff="203.0.113.10", trusted_proxy_ips=("10.0.0.1",))
    assert client_rate_limit_key(request) == "172.18.0.2"


def test_rate_limit_uses_rightmost_untrusted_forwarded_for_from_trusted_proxy() -> None:
    request = _request(
        peer="10.0.0.1",
        xff="198.51.100.20, 203.0.113.7, 10.0.0.1",
        trusted_proxy_ips=("10.0.0.0/24",),
    )
    assert client_rate_limit_key(request) == "203.0.113.7"
