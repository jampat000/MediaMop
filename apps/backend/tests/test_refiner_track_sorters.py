"""An ordered sorter list replaces the fixed ranking tuple.

The load-bearing test here is ``test_the_seeded_default_ranks_identically_to_the_old_tuple``.
Everything else is new capability; that one proves the capability arrived without
changing what any existing install does, and it asserts against a **copy of the original
implementation** rather than against a description of it (#341).
"""

from __future__ import annotations

import itertools
import json

import pytest

from mediamop.modules.refiner.refiner_track_sorters import (
    DEFAULT_AUDIO_SORTERS,
    SORTER_FIELDS,
    TrackSorter,
    TrackSorterError,
    describe_sorters,
    dump_sorters,
    parse_sorters,
    preset_sorters,
    sort_key_for_track,
    validate_sorters,
)


def _original_quality_sort_key(track: dict, *, fallback_preferred_penalty: int | None = None) -> tuple[int, ...]:
    """The ranking exactly as it was before this change.

    Copied verbatim from ``_quality_sort_key`` so the equivalence test compares against
    the real thing rather than against my reading of it.
    """

    com = 1 if track["commentary"] else 0
    ch = int(track["channels"]) if track["channels"] and track["channels"] > 0 else 0
    ch_unknown = 1 if ch <= 0 else 0
    ch_score = -min(ch, 64) if ch > 0 else 0
    cr = int(track["codec_rank"])
    br = int(track["bitrate"]) if track["bitrate"] and track["bitrate"] > 0 else 0
    br_unknown = 1 if br <= 0 else 0
    br_score = -min(br, 2_000_000_000) if br > 0 else 0
    default_weak = 0 if track["default"] else 1
    idx = int(track["index"])
    fp = 0 if fallback_preferred_penalty is None else int(fallback_preferred_penalty)
    return (fp, com, ch_unknown, ch_score, cr, br_unknown, br_score, default_weak, idx)


def _track(**over) -> dict:
    base = {
        "index": 0,
        "language": "eng",
        "title": "",
        "commentary": False,
        "default": False,
        "forced": False,
        "channels": 6,
        "bitrate": 640_000,
        "codec": "eac3",
        "codec_rank": 3,
    }
    base.update(over)
    return base


# --- the equivalence that matters ----------------------------------------------------


def test_the_seeded_default_ranks_identically_to_the_old_tuple() -> None:
    """Nothing changes on upgrade until somebody edits the list.

    Every combination of the facts the old tuple looked at, ranked both ways. The
    *orderings* must match; the key tuples themselves are a different shape and are not
    expected to be equal.
    """

    combinations = itertools.product(
        (False, True),
        (0, 2, 6, 8),
        (1, 3, 5),
        (0, 128_000, 640_000),
        (False, True),
    )
    tracks = [
        _track(
            index=index,
            commentary=commentary,
            channels=channels,
            codec_rank=codec_rank,
            bitrate=bitrate,
            default=is_default,
        )
        for index, (commentary, channels, codec_rank, bitrate, is_default) in enumerate(combinations)
    ]

    by_new = sorted(tracks, key=lambda t: sort_key_for_track(list(DEFAULT_AUDIO_SORTERS), t))
    by_old = sorted(tracks, key=_original_quality_sort_key)

    assert [t["index"] for t in by_new] == [t["index"] for t in by_old]


def test_the_two_rankings_agree_on_the_single_best_track() -> None:
    tracks = [
        _track(index=0, channels=2, codec_rank=5, bitrate=128_000),
        _track(index=1, channels=8, codec_rank=1, bitrate=1_500_000),
        _track(index=2, channels=8, codec_rank=1, bitrate=1_500_000, commentary=True),
    ]

    best_new = min(tracks, key=lambda t: sort_key_for_track(list(DEFAULT_AUDIO_SORTERS), t))
    best_old = min(tracks, key=_original_quality_sort_key)

    assert best_new["index"] == best_old["index"] == 1


# --- what the list can now express that the tuple could not --------------------------


def test_an_operator_can_prefer_a_specific_codec() -> None:
    """ "Prefer DTS-HD over TrueHD" was a code change before this."""

    sorters = [TrackSorter(field="codec", value="dts")]
    truehd = _track(index=0, codec="truehd")
    dts = _track(index=1, codec="dts")

    best = min([truehd, dts], key=lambda t: sort_key_for_track(sorters, t))

    assert best["codec"] == "dts"


def test_an_operator_can_prefer_five_one_over_seven_one() -> None:
    """The other example from the issue, and the reason channels accepts 5.1 notation."""

    sorters = [TrackSorter(field="channels", value="=5.1")]
    seven_one = _track(index=0, channels=8)
    five_one = _track(index=1, channels=6)

    best = min([seven_one, five_one], key=lambda t: sort_key_for_track(sorters, t))

    assert best["channels"] == 6


def test_an_operator_can_demote_a_title_containing_a_word() -> None:
    sorters = [TrackSorter(field="title", value="descriptive", reversed=True)]
    descriptive = _track(index=0, title="English Descriptive Audio")
    plain = _track(index=1, title="English")

    best = min([descriptive, plain], key=lambda t: sort_key_for_track(sorters, t))

    assert best["title"] == "English"


def test_language_first_then_channels_is_the_flow_the_issue_describes() -> None:
    """The live FileFlows Movie Flow: Language = eng, then Channels >= 5.1."""

    sorters = [TrackSorter(field="language", value="eng"), TrackSorter(field="channels", value=">=5.1")]
    fre_71 = _track(index=0, language="fre", channels=8)
    eng_20 = _track(index=1, language="eng", channels=2)
    eng_51 = _track(index=2, language="eng", channels=6)

    ranked = sorted([fre_71, eng_20, eng_51], key=lambda t: sort_key_for_track(sorters, t))

    assert [t["index"] for t in ranked] == [2, 1, 0]


def test_reversed_flips_a_natural_ordering() -> None:
    sorters = [TrackSorter(field="bitrate", reversed=True)]
    big = _track(index=0, bitrate=1_500_000)
    small = _track(index=1, bitrate=128_000)

    best = min([big, small], key=lambda t: sort_key_for_track(sorters, t))

    assert best["bitrate"] == 128_000


def test_an_unknown_value_sorts_after_a_known_one_in_both_directions() -> None:
    """ "No bitrate reported" is not the same as "the lowest bitrate"."""

    known = _track(index=0, bitrate=128_000)
    unknown = _track(index=1, bitrate=0)

    ascending = sorted([unknown, known], key=lambda t: sort_key_for_track([TrackSorter(field="bitrate")], t))
    descending = sorted(
        [unknown, known], key=lambda t: sort_key_for_track([TrackSorter(field="bitrate", reversed=True)], t)
    )

    assert ascending[0]["index"] == 0
    assert descending[0]["index"] == 0


def test_channels_accepts_the_notation_operators_actually_write() -> None:
    sorters = [TrackSorter(field="channels", value=">=5.1")]

    assert sort_key_for_track(sorters, _track(channels=6))[0] == 0
    assert sort_key_for_track(sorters, _track(channels=8))[0] == 0
    assert sort_key_for_track(sorters, _track(channels=2))[0] == 1
    # Words too, because "stereo" is how people say it.
    assert sort_key_for_track([TrackSorter(field="channels", value="stereo")], _track(channels=2))[0] == 0


def test_the_index_is_always_the_final_tiebreak() -> None:
    """Two identical tracks must resolve the same way every time, not by dict order."""

    a = _track(index=3)
    b = _track(index=1)

    ranked = sorted([a, b], key=lambda t: sort_key_for_track(list(DEFAULT_AUDIO_SORTERS), t))

    assert [t["index"] for t in ranked] == [1, 3]


def test_an_empty_sorter_list_still_produces_a_total_order() -> None:
    ranked = sorted([_track(index=2), _track(index=0)], key=lambda t: sort_key_for_track([], t))

    assert [t["index"] for t in ranked] == [0, 2]


# --- storage -------------------------------------------------------------------------


def test_a_list_round_trips(session: None = None) -> None:
    original = [TrackSorter(field="language", value="eng"), TrackSorter(field="channels", reversed=True)]

    assert parse_sorters(dump_sorters(original)) == original


def test_an_unusable_stored_value_falls_back_to_the_seeded_default() -> None:
    """Never to an empty list: that would rank by index alone and silently change answers."""

    for bad in ("", "   ", "not json", '"a string"', "[]", "[1, 2, 3]"):
        assert parse_sorters(bad) == list(DEFAULT_AUDIO_SORTERS)


def test_an_unknown_field_in_stored_data_is_skipped_rather_than_crashing() -> None:
    stored = json.dumps([{"field": "loudness"}, {"field": "channels"}])

    assert parse_sorters(stored) == [TrackSorter(field="channels")]


def test_saving_an_unknown_field_is_refused_rather_than_silently_dropped() -> None:
    """A saved list quietly missing what an operator typed would change ranking unannounced."""

    with pytest.raises(TrackSorterError, match="unknown field"):
        validate_sorters(json.dumps([{"field": "loudness"}]))


def test_saving_something_that_is_not_a_list_is_refused() -> None:
    with pytest.raises(TrackSorterError, match="must be a list"):
        validate_sorters(json.dumps({"field": "channels"}))

    with pytest.raises(TrackSorterError, match="not valid JSON"):
        validate_sorters("{{{")


def test_saving_nothing_yields_the_seeded_default() -> None:
    assert parse_sorters(validate_sorters("")) == list(DEFAULT_AUDIO_SORTERS)


def test_every_documented_field_is_accepted() -> None:
    stored = json.dumps([{"field": name} for name in SORTER_FIELDS])

    assert len(parse_sorters(stored)) == len(SORTER_FIELDS)


# --- presets and notes ---------------------------------------------------------------


def test_the_existing_policies_become_presets_that_fill_the_list() -> None:
    assert preset_sorters("preferred_langs_quality") == list(DEFAULT_AUDIO_SORTERS)
    assert preset_sorters("quality_all_languages")[0].field == "commentary"
    # An unknown name gets the safe default rather than nothing.
    assert preset_sorters("something-else") == list(DEFAULT_AUDIO_SORTERS)


def test_the_notes_describe_the_configured_list_rather_than_a_fixed_sentence() -> None:
    """Refiner explains *why* it picked a track. That has to keep working now it is data."""

    text = describe_sorters([TrackSorter(field="language", value="eng"), TrackSorter(field="channels")])

    assert "language eng" in text
    assert "channels" in text
    assert ", then " in text


def test_the_notes_say_so_when_nothing_is_configured() -> None:
    assert "file order" in describe_sorters([])


def test_a_negated_match_is_described_as_a_negation() -> None:
    assert describe_sorters([TrackSorter(field="title", value="commentary", reversed=True)]) == ("not title commentary")


def test_choosing_a_policy_fills_the_sorter_list_so_it_can_then_be_edited() -> None:
    """What makes the policies presets rather than a separate mechanism.

    Previously the policy was the only thing an operator could change; now picking one
    shows them the sorters it stands for.
    """

    filled = parse_sorters(dump_sorters(preset_sorters("quality_all_languages")))

    assert [s.field for s in filled] == ["commentary", "channels", "codec", "bitrate"]
    # And the default policy fills with exactly the ranking that has always applied.
    assert preset_sorters("preferred_langs_quality") == list(DEFAULT_AUDIO_SORTERS)
