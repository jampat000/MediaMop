from mediamop.modules.pruner import pruner_media_library


def test_jellyfin_emby_connection_test_rejects_missing_api_key() -> None:
    ok, message = pruner_media_library.test_emby_jellyfin_connection(base_url="http://server.test", api_key="")
    assert ok is False
    assert "API key is missing" in message


def test_jellyfin_emby_connection_test_uses_authenticated_users_endpoint(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, *, headers: dict[str, str], timeout_sec: float = 20.0):
        calls.append((url, headers))
        return 200, [{"Name": "Admin"}]

    monkeypatch.setattr(pruner_media_library, "http_get_json", fake_get)

    ok, message = pruner_media_library.test_emby_jellyfin_connection(
        base_url="http://server.test",
        api_key="real-key",
    )

    assert ok is True
    assert message == "Authenticated API key accepted"
    assert calls == [("http://server.test/Users", {"X-Emby-Token": "real-key", "Accept": "application/json"})]


def test_jellyfin_emby_connection_test_rejects_auth_failures(monkeypatch) -> None:
    def fake_get(url: str, *, headers: dict[str, str], timeout_sec: float = 20.0):
        return 401, {"error": "bad key"}

    monkeypatch.setattr(pruner_media_library, "http_get_json", fake_get)

    ok, message = pruner_media_library.test_emby_jellyfin_connection(
        base_url="http://server.test",
        api_key="bad-key",
    )

    assert ok is False
    assert "Authentication failed" in message
