"""Tests for :mod:`mediamop.modules.broker.broker_client_registry`."""

from __future__ import annotations

from types import SimpleNamespace

from mediamop.modules.broker.broker_client_newznab import BrokerNewznabClient
from mediamop.modules.broker.broker_client_registry import (
    ALL_NATIVE_CLIENTS,
    NATIVE_CLIENT_BY_SLUG,
    get_client_for_indexer,
)
from mediamop.modules.broker.broker_client_torznab import BrokerTorznabClient


def test_all_native_clients_count() -> None:
    assert len(ALL_NATIVE_CLIENTS) == 40


def test_native_slugs_unique() -> None:
    slugs = [c.slug for c in ALL_NATIVE_CLIENTS]
    assert len(slugs) == len(set(slugs))


def test_native_client_by_slug_matches() -> None:
    assert NATIVE_CLIENT_BY_SLUG["native__yts"].slug == "native__yts"


def test_get_client_native_yts() -> None:
    row = SimpleNamespace(
        id=1,
        kind="native__yts",
        slug="native__yts",
        url="",
        api_key="",
        protocol="torrent",
    )
    c = get_client_for_indexer(row)
    assert c is not None
    assert c.slug == "native__yts"


def test_get_client_torznab() -> None:
    row = SimpleNamespace(
        id=1,
        kind="torznab",
        slug="custom__torznab",
        url="https://example.com/torznab",
        api_key="k",
        protocol="torrent",
    )
    c = get_client_for_indexer(row)
    assert isinstance(c, BrokerTorznabClient)
    assert c.slug == "custom__torznab"


def test_get_client_newznab() -> None:
    row = SimpleNamespace(
        id=1,
        kind="newznab",
        slug="my_nzb",
        url="https://indexer.example",
        api_key="abc",
        protocol="usenet",
    )
    c = get_client_for_indexer(row)
    assert isinstance(c, BrokerNewznabClient)
    assert c.slug == "my_nzb"


def test_get_client_unknown_kind() -> None:
    row = SimpleNamespace(
        id=1,
        kind="unknown_kind",
        slug="x",
        url="",
        api_key="",
        protocol="torrent",
    )
    assert get_client_for_indexer(row) is None


def test_get_client_unknown_native_slug() -> None:
    row = SimpleNamespace(
        id=1,
        kind="native__does_not_exist",
        slug="x",
        url="",
        api_key="",
        protocol="torrent",
    )
    assert get_client_for_indexer(row) is None
