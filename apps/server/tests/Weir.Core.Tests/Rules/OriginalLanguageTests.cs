using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Ported from <c>apps/backend/tests/test_refiner_original_language.py</c>: the selection and
/// language-code mapping tests. The TMDb provider tests (HTTP, caching, SSRF refusal) belong to
/// the metadata provider port and are not here.
/// </summary>
public sealed class OriginalLanguageTests
{
    private static LookupResult Matched(string language) => new()
    {
        Status = LookupResult.StatusMatched,
        Metadata = new TitleMetadata { OriginalLanguage = language, Title = "Film", Year = 2001 },
        Detail = "matched",
    };

    private static OriginalLanguageTrack T(int index, string language) => new(index, language);

    private static OriginalLanguageOutcome Select(OriginalLanguageRules rules, LookupResult lookup, params OriginalLanguageTrack[] tracks) =>
        OriginalLanguage.SelectTracks(rules, lookup, tracks);

    // --- selection -----------------------------------------------------------------------

    [Fact]
    public void The_original_language_wins_over_the_preference_list()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true }, Matched("fr"), T(0, "eng"), T(1, "fre"));

        Assert.True(outcome.Chose);
        Assert.Equal([1], outcome.PreferredIndices);
        Assert.Contains("original language (fre)", outcome.Note, StringComparison.Ordinal);
    }

    [Fact]
    public void Additional_languages_are_kept_alongside_the_original()
    {
        var outcome = Select(
            new OriginalLanguageRules { Enabled = true, AdditionalLanguages = ["eng"], KeepOnlyFirst = true },
            Matched("es"),
            T(0, "eng"), T(1, "eng"), T(2, "spa"), T(3, "spa"), T(4, "spa"), T(5, "ger"));

        Assert.Equal([2, 0], outcome.PreferredIndices);
    }

    [Fact]
    public void Keep_only_first_off_keeps_every_track_of_each_language()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true, KeepOnlyFirst = false }, Matched("es"), T(0, "spa"), T(1, "spa"), T(2, "eng"));

        Assert.Equal([0, 1], outcome.PreferredIndices);
    }

    [Fact]
    public void The_original_language_comes_before_the_additional_ones()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true, AdditionalLanguages = ["eng"] }, Matched("ja"), T(0, "eng"), T(1, "jpn"));

        Assert.Equal([1, 0], outcome.PreferredIndices);
    }

    // --- the untagged track --------------------------------------------------------------

    [Fact]
    public void An_untagged_track_is_ignored_by_default()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true, TreatEmptyAsOriginal = false }, Matched("fr"), T(0, ""), T(1, "eng"));

        Assert.False(outcome.Chose);
    }

    [Fact]
    public void An_untagged_track_counts_as_the_original_when_configured()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true, TreatEmptyAsOriginal = true }, Matched("fr"), T(0, ""), T(1, "eng"));

        Assert.Equal([0], outcome.PreferredIndices);
    }

    // --- declining, which must never lose the audio --------------------------------------

    [Fact]
    public void Disabled_declines_silently_and_changes_nothing()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = false }, Matched("fr"), T(0, "eng"));

        Assert.False(outcome.Chose);
        Assert.Equal("", outcome.Note);
    }

    [Fact]
    public void No_match_declines_and_says_the_preferences_chose()
    {
        var outcome = Select(
            new OriginalLanguageRules { Enabled = true },
            new LookupResult { Status = LookupResult.StatusNoMatch, Detail = "The metadata provider had no match for Film." },
            T(0, "eng"));

        Assert.False(outcome.Chose);
        Assert.Contains("no match", outcome.Note, StringComparison.Ordinal);
        Assert.Contains("language preferences chose the track", outcome.Note, StringComparison.Ordinal);
    }

    [Fact]
    public void An_unreachable_provider_declines_and_says_so()
    {
        var outcome = Select(
            new OriginalLanguageRules { Enabled = true },
            new LookupResult { Status = LookupResult.StatusUnreachable, Detail = "Weir could not reach the metadata provider." },
            T(0, "eng"));

        Assert.False(outcome.Chose);
        Assert.Contains("could not reach", outcome.Note, StringComparison.Ordinal);
    }

    [Fact]
    public void No_provider_configured_declines_and_says_so()
    {
        var outcome = Select(
            new OriginalLanguageRules { Enabled = true },
            new LookupResult { Status = LookupResult.StatusNotConfigured, Detail = "No metadata provider key is configured." },
            T(0, "eng"));

        Assert.False(outcome.Chose);
        Assert.Contains("No metadata provider key is configured", outcome.Note, StringComparison.Ordinal);
    }

    [Fact]
    public void A_match_with_no_original_language_declines()
    {
        var outcome = Select(
            new OriginalLanguageRules { Enabled = true },
            new LookupResult { Status = LookupResult.StatusMatched, Metadata = new TitleMetadata { OriginalLanguage = "" }, Detail = "" },
            T(0, "eng"));

        Assert.False(outcome.Chose);
        Assert.Contains("no original language", outcome.Note, StringComparison.Ordinal);
    }

    [Fact]
    public void First_if_none_declines_so_the_callers_fallback_keeps_the_audio()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true, FirstIfNone = true }, Matched("fr"), T(0, "eng"), T(1, "ger"));

        Assert.False(outcome.Chose);
        Assert.Contains("still has audio", outcome.Note, StringComparison.Ordinal);
    }

    [Fact]
    public void First_if_none_off_still_declines_rather_than_removing_everything()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true, FirstIfNone = false }, Matched("fr"), T(0, "eng"));

        Assert.False(outcome.Chose);
        Assert.Contains("language preferences chose the track", outcome.Note, StringComparison.Ordinal);
    }

    [Fact]
    public void Additional_languages_are_normalised_and_deduplicated()
    {
        Assert.Equal(["eng", "fre"], OriginalLanguage.ParseAdditionalLanguages("en, FR ,en, "));
        Assert.Empty(OriginalLanguage.ParseAdditionalLanguages(""));
    }

    // --- language codes ------------------------------------------------------------------

    [Theory]
    [InlineData("fr", "fre")]
    [InlineData("fr", "fra")]
    [InlineData("de", "ger")]
    [InlineData("de", "deu")]
    [InlineData("es", "spa")]
    [InlineData("ja", "jpn")]
    [InlineData("zh", "zho")]
    public void Provider_and_file_language_codes_are_matched_across_standards(string providerCode, string fileCode) =>
        Assert.Equal(OriginalLanguage.CanonicalLanguage(providerCode), OriginalLanguage.CanonicalLanguage(fileCode));

    [Fact]
    public void A_language_weir_does_not_know_still_matches_itself()
    {
        Assert.Equal(OriginalLanguage.CanonicalLanguage("qaa"), OriginalLanguage.CanonicalLanguage("qaa"));
        Assert.Equal("qaa", OriginalLanguage.CanonicalLanguage("qaa"));
    }

    [Fact]
    public void A_film_tagged_in_the_other_standard_still_keeps_its_original_audio()
    {
        var outcome = Select(new OriginalLanguageRules { Enabled = true }, Matched("fr"), T(0, "eng"), T(1, "fra"));

        Assert.Equal([1], outcome.PreferredIndices);
    }

    [Fact]
    public void The_canonical_form_is_stable_across_processes()
    {
        Assert.Equal("fre", OriginalLanguage.CanonicalLanguage("fr"));
        Assert.Equal("fre", OriginalLanguage.CanonicalLanguage("fra"));
        Assert.Equal("ger", OriginalLanguage.CanonicalLanguage("de"));
        Assert.Equal("ger", OriginalLanguage.CanonicalLanguage("deu"));
    }
}
