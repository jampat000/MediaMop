"""Keeping the original-language audio instead of whatever the preference list says.

For a French film with English and French audio, an ``eng``-first preference keeps **the
dub**. Most people who care about audio quality want the original, and nothing in MediaMop
knew what the original was (#343).

The rule that matters most: this module only ever *reorders*. ``plan_remux`` already
refuses to write a file with no audio, and nothing here may weaken that — so declining is
a first-class outcome and the caller's existing fallback still runs.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

from mediamop.integrations.metadata.provider_port import LookupResult, TitleMetadata
from mediamop.integrations.metadata.tmdb_provider import (
    DEFAULT_TMDB_BASE_URL,
    TmdbMetadataProvider,
    clear_metadata_cache,
)
from mediamop.modules.refiner.refiner_original_language import (
    OriginalLanguageRules,
    parse_additional_languages,
    select_original_language_tracks,
)


def _matched(language: str) -> LookupResult:
    return LookupResult(
        status="matched",
        metadata=TitleMetadata(original_language=language, title="Film", year=2001),
        detail="matched",
    )


def _track(index: int, language: str) -> dict:
    return {"index": index, "language": language}


# --- selection -----------------------------------------------------------------------


def test_the_original_language_wins_over_the_preference_list() -> None:
    """The whole point: an eng-first preference would have kept the dub."""

    tracks = [_track(0, "eng"), _track(1, "fre")]

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True), lookup=_matched("fr"), tracks=tracks
    )

    assert outcome.chose is True
    assert outcome.preferred_indices == (1,)
    assert "original language (fre)" in outcome.note


def test_additional_languages_are_kept_alongside_the_original() -> None:
    """The worked example from the element's own help text.

    Two English tracks, three Spanish, one German; original language Spanish; additional
    languages eng — one English and one Spanish track.
    """

    tracks = [
        _track(0, "eng"),
        _track(1, "eng"),
        _track(2, "spa"),
        _track(3, "spa"),
        _track(4, "spa"),
        _track(5, "ger"),
    ]

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True, additional_languages=("eng",), keep_only_first=True),
        lookup=_matched("es"),
        tracks=tracks,
    )

    assert outcome.preferred_indices == (2, 0)


def test_keep_only_first_off_keeps_every_track_of_each_language() -> None:
    tracks = [_track(0, "spa"), _track(1, "spa"), _track(2, "eng")]

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True, keep_only_first=False),
        lookup=_matched("es"),
        tracks=tracks,
    )

    assert outcome.preferred_indices == (0, 1)


def test_the_original_language_comes_before_the_additional_ones() -> None:
    tracks = [_track(0, "eng"), _track(1, "jpn")]

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True, additional_languages=("eng",)),
        lookup=_matched("ja"),
        tracks=tracks,
    )

    assert outcome.preferred_indices == (1, 0)


# --- the untagged track --------------------------------------------------------------


def test_an_untagged_track_is_ignored_by_default() -> None:
    tracks = [_track(0, ""), _track(1, "eng")]

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True, treat_empty_as_original=False),
        lookup=_matched("fr"),
        tracks=tracks,
    )

    assert outcome.chose is False


def test_an_untagged_track_counts_as_the_original_when_configured() -> None:
    tracks = [_track(0, ""), _track(1, "eng")]

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True, treat_empty_as_original=True),
        lookup=_matched("fr"),
        tracks=tracks,
    )

    assert outcome.preferred_indices == (0,)


# --- declining, which must never lose the audio --------------------------------------


def test_disabled_declines_silently_and_changes_nothing() -> None:
    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=False), lookup=_matched("fr"), tracks=[_track(0, "eng")]
    )

    assert outcome.chose is False
    assert outcome.note == ""


def test_no_match_declines_and_says_the_preferences_chose() -> None:
    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True),
        lookup=LookupResult(status="no_match", detail="The metadata provider had no match for Film."),
        tracks=[_track(0, "eng")],
    )

    assert outcome.chose is False
    assert "no match" in outcome.note
    assert "language preferences chose the track" in outcome.note


def test_an_unreachable_provider_declines_and_says_so() -> None:
    """The operator needs to know the provider was asked and failed, not that it was skipped."""

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True),
        lookup=LookupResult(status="unreachable", detail="MediaMop could not reach the metadata provider."),
        tracks=[_track(0, "eng")],
    )

    assert outcome.chose is False
    assert "could not reach" in outcome.note


def test_no_provider_configured_declines_and_says_so() -> None:
    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True),
        lookup=LookupResult(status="not_configured", detail="No metadata provider key is configured."),
        tracks=[_track(0, "eng")],
    )

    assert outcome.chose is False
    assert "No metadata provider key is configured" in outcome.note


def test_a_match_with_no_original_language_declines() -> None:
    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True),
        lookup=LookupResult(status="matched", metadata=TitleMetadata(original_language=""), detail=""),
        tracks=[_track(0, "eng")],
    )

    assert outcome.chose is False
    assert "no original language" in outcome.note


def test_first_if_none_declines_so_the_callers_fallback_keeps_the_audio() -> None:
    """The safety net.

    It reorders nothing — it declines in a way that says so, leaving the caller's own
    fallback to pick. That is what guarantees the output still has audio.
    """

    tracks = [_track(0, "eng"), _track(1, "ger")]

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True, first_if_none=True), lookup=_matched("fr"), tracks=tracks
    )

    assert outcome.chose is False
    assert "still has audio" in outcome.note


def test_first_if_none_off_still_declines_rather_than_removing_everything() -> None:
    """Even with the safety net off, this module never leaves a file with no audio."""

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True, first_if_none=False),
        lookup=_matched("fr"),
        tracks=[_track(0, "eng")],
    )

    assert outcome.chose is False
    assert "language preferences chose the track" in outcome.note


def test_additional_languages_are_normalised_and_deduplicated() -> None:
    assert parse_additional_languages("en, FR ,en, ") == ("eng", "fre")
    assert parse_additional_languages("") == ()


# --- the provider --------------------------------------------------------------------


class _Response:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def _search_payload(language: str = "fr") -> dict:
    return {
        "results": [
            {"id": 42, "title": "Film", "original_language": language, "release_date": "2001-05-01"},
        ]
    }


def test_a_lookup_returns_the_original_language() -> None:
    clear_metadata_cache()
    provider = TmdbMetadataProvider(api_key="k")

    with patch("urllib.request.urlopen", return_value=_Response(_search_payload())):
        result = provider.lookup_movie(title="Film", year=2001)

    assert result.matched is True
    assert result.metadata is not None
    assert result.metadata.original_language == "fr"
    assert result.metadata.year == 2001


def test_a_repeated_lookup_is_served_from_the_cache() -> None:
    """One HTTP call per file per pass is the storm this exists to prevent."""

    clear_metadata_cache()
    provider = TmdbMetadataProvider(api_key="k")

    with patch("urllib.request.urlopen", return_value=_Response(_search_payload())) as opened:
        provider.lookup_movie(title="Film", year=2001)
        provider.lookup_movie(title="Film", year=2001)

    assert opened.call_count == 1


def test_a_negative_answer_is_cached_too() -> None:
    """A title the provider does not know will still be unknown on the next file."""

    clear_metadata_cache()
    provider = TmdbMetadataProvider(api_key="k")

    with patch("urllib.request.urlopen", return_value=_Response({"results": []})) as opened:
        first = provider.lookup_movie(title="Unknown", year=1999)
        provider.lookup_movie(title="Unknown", year=1999)

    assert first.status == "no_match"
    assert opened.call_count == 1


def test_no_key_reports_not_configured_without_a_call() -> None:
    clear_metadata_cache()
    provider = TmdbMetadataProvider(api_key="")

    with patch("urllib.request.urlopen") as opened:
        result = provider.lookup_movie(title="Film", year=2001)

    assert result.status == "not_configured"
    assert opened.call_count == 0


def test_a_provider_that_is_down_reports_unreachable_rather_than_raising() -> None:
    clear_metadata_cache()
    provider = TmdbMetadataProvider(api_key="k")

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        result = provider.lookup_movie(title="Film", year=2001)

    assert result.status == "unreachable"
    assert "could not reach" in result.detail


def test_a_rejected_key_is_reported_as_configuration_not_an_outage() -> None:
    """Saying "unreachable" would send an operator to look at their network."""

    clear_metadata_cache()
    provider = TmdbMetadataProvider(api_key="wrong")
    error = urllib.error.HTTPError(url="u", code=401, msg="Unauthorized", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=error):
        result = provider.lookup_movie(title="Film", year=2001)

    assert result.status == "not_configured"
    assert "rejected the configured key" in result.detail


def test_a_gateway_address_is_accepted_and_a_private_one_is_refused() -> None:
    """An operator may put a cache or gateway in front of the provider.

    Hardcoding the vendor address would make that setup unusable; accepting anything at
    all would make the setting an SSRF hole.
    """

    clear_metadata_cache()
    gateway = TmdbMetadataProvider(api_key="k", base_url="https://metadata.example.workers.dev")
    with patch("urllib.request.urlopen", return_value=_Response(_search_payload())):
        assert gateway.lookup_movie(title="Film", year=2001).matched is True

    clear_metadata_cache()
    internal = TmdbMetadataProvider(api_key="k", base_url="http://169.254.169.254/latest")
    result = internal.lookup_movie(title="Film", year=2001)

    assert result.status == "not_configured"
    assert "not usable" in result.detail


def test_the_default_base_url_is_the_provider_itself() -> None:
    assert DEFAULT_TMDB_BASE_URL.startswith("https://")


def test_unreadable_json_is_reported_rather_than_raising() -> None:
    clear_metadata_cache()
    provider = TmdbMetadataProvider(api_key="k")

    class _Bad:
        def read(self) -> bytes:
            return b"not json"

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    with patch("urllib.request.urlopen", return_value=_Bad()):
        result = provider.lookup_movie(title="Film", year=2001)

    assert result.status == "unreachable"
    assert "unreadable" in result.detail


def test_provider_and_file_language_codes_are_matched_across_standards() -> None:
    """Providers report ISO 639-1; files are usually tagged ISO 639-2.

    Without this the feature would look configured and silently never match, which is the
    worst kind of not working. The bibliographic and terminological 639-2 variants
    (fre/fra, ger/deu) have to agree too.
    """

    from mediamop.modules.refiner.refiner_original_language import canonical_language

    for provider_code, file_code in (
        ("fr", "fre"),
        ("fr", "fra"),
        ("de", "ger"),
        ("de", "deu"),
        ("es", "spa"),
        ("ja", "jpn"),
        ("zh", "zho"),
    ):
        assert canonical_language(provider_code) == canonical_language(file_code), provider_code


def test_a_language_mediamop_does_not_know_still_matches_itself() -> None:
    from mediamop.modules.refiner.refiner_original_language import canonical_language

    assert canonical_language("qaa") == canonical_language("qaa")
    assert canonical_language("qaa") == "qaa"


def test_a_film_tagged_in_the_other_standard_still_keeps_its_original_audio() -> None:
    """The end-to-end version of the mapping: TMDb says 'fr', the file says 'fre'."""

    outcome = select_original_language_tracks(
        rules=OriginalLanguageRules(enabled=True),
        lookup=_matched("fr"),
        tracks=[_track(0, "eng"), _track(1, "fra")],
    )

    assert outcome.preferred_indices == (1,)


def test_the_canonical_form_is_stable_across_processes() -> None:
    """A set would pick between two equal-length codes by hash order, which varies by
    process — the same file could be described differently on different runs."""

    from mediamop.modules.refiner.refiner_original_language import canonical_language

    # The bibliographic form, which is what media files are tagged with.
    assert canonical_language("fr") == "fre"
    assert canonical_language("fra") == "fre"
    assert canonical_language("de") == "ger"
    assert canonical_language("deu") == "ger"
