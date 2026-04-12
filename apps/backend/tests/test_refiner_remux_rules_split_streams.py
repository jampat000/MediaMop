"""Sanity checks for ported Refiner remux rules helpers."""

from __future__ import annotations

from mediamop.modules.refiner.refiner_remux_rules import split_streams


def test_split_streams_orders_by_index() -> None:
    probe = {
        "streams": [
            {"index": 2, "codec_type": "audio"},
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "subtitle"},
        ],
    }
    v, a, s = split_streams(probe)
    assert [x["index"] for x in v] == [0]
    assert [x["index"] for x in a] == [2]
    assert [x["index"] for x in s] == [1]
