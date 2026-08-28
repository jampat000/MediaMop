"""Shared queue-row plumbing only (paths, no per-scope or per-product mapping)."""

from __future__ import annotations

from mediamop.modules.refiner import normalize_storage_path


def test_normalize_storage_path_contract() -> None:
    assert normalize_storage_path(r"E:\Foo\Bar.mkv") == "e:/foo/bar.mkv"
