using Weir.Core.LibraryMode;

namespace Weir.Core.Tests.LibraryMode;

public sealed class RedownloadRiskEvaluatorTests
{
    private static CustomFormatSnapshot MultiAudioFormat(long id = 1) => new(
        id,
        "Multi-Audio",
        [new FormatSpecificationSnapshot(RedownloadRiskEvaluator.LanguageImplementation, Negate: false, LanguageCode: "eng", ExceptLanguage: true)]);

    private static CustomFormatSnapshot JapaneseAudioFormat(long id = 2) => new(
        id,
        "Japanese Audio",
        [new FormatSpecificationSnapshot(RedownloadRiskEvaluator.LanguageImplementation, Negate: false, LanguageCode: "jpn", ExceptLanguage: false)]);

    [Fact]
    public void Losing_a_format_that_drops_the_score_below_cutoff_warns_in_the_issues_exact_wording()
    {
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [MultiAudioFormat()], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(UpgradeAllowed: true, CutoffFormatScore: 60, FormatScores: new Dictionary<long, int> { [1] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate(
            "Radarr", "Blade Runner 2049", snapshot, profile, removedAudioLanguages: ["jpn"], skipIfManagerWouldRedownload: true);

        Assert.True(result.RiskDetected);
        Assert.True(result.SkipRecommended);
        Assert.Equal(50, result.PredictedScore);
        var warning = Assert.Single(result.Warnings);
        Assert.Equal("Radarr may download Blade Runner 2049 again: its 'Multi-Audio' format (+50) would no longer match.", warning.Message);
    }

    [Fact]
    public void Skip_recommended_is_false_when_the_library_does_not_ask_to_skip_on_risk()
    {
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [MultiAudioFormat()], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 60, new Dictionary<long, int> { [1] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate(
            "Radarr", "Blade Runner 2049", snapshot, profile, ["jpn"], skipIfManagerWouldRedownload: false);

        Assert.True(result.RiskDetected);
        Assert.False(result.SkipRecommended);
        Assert.Single(result.Warnings);
    }

    [Fact]
    public void Losing_a_format_that_does_not_drop_the_score_below_cutoff_is_not_a_warning()
    {
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [MultiAudioFormat()], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(UpgradeAllowed: true, CutoffFormatScore: 40, FormatScores: new Dictionary<long, int> { [1] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate(
            "Radarr", "Blade Runner 2049", snapshot, profile, removedAudioLanguages: ["jpn"], skipIfManagerWouldRedownload: true);

        Assert.False(result.RiskDetected);
        Assert.False(result.SkipRecommended);
        Assert.Empty(result.Warnings);
        Assert.Equal(50, result.PredictedScore);
    }

    [Fact]
    public void Upgrades_not_allowed_never_warns_even_below_cutoff()
    {
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [MultiAudioFormat()], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(UpgradeAllowed: false, CutoffFormatScore: 60, FormatScores: new Dictionary<long, int> { [1] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate("Radarr", "Blade Runner 2049", snapshot, profile, ["jpn"], true);

        Assert.False(result.RiskDetected);
        Assert.Empty(result.Warnings);
    }

    [Fact]
    public void A_language_specific_format_is_lost_when_its_own_language_is_removed()
    {
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [JapaneseAudioFormat()], CustomFormatScore: 40);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 30, new Dictionary<long, int> { [2] = 40 });

        var result = RedownloadRiskEvaluator.Evaluate("Sonarr", "Some Show", snapshot, profile, ["jpn"], true);

        Assert.True(result.RiskDetected);
        var warning = Assert.Single(result.Warnings);
        Assert.Equal("Japanese Audio", warning.FormatName);
        Assert.Equal(40, warning.FormatScore);
    }

    [Fact]
    public void Removing_a_different_language_does_not_affect_a_language_specific_format()
    {
        var snapshot = new FileFormatSnapshot(["eng", "jpn", "ger"], [JapaneseAudioFormat()], CustomFormatScore: 40);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 30, new Dictionary<long, int> { [2] = 40 });

        var result = RedownloadRiskEvaluator.Evaluate("Sonarr", "Some Show", snapshot, profile, ["ger"], true);

        Assert.False(result.RiskDetected);
        Assert.Empty(result.Warnings);
        Assert.Equal(40, result.PredictedScore);
    }

    [Fact]
    public void An_unrecognised_specification_implementation_cannot_tell_rather_than_assuming_unaffected()
    {
        var mystery = new CustomFormatSnapshot(3, "Mystery Format", [new FormatSpecificationSnapshot("SomeFutureSpecType", false, null, false)]);
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [mystery], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 60, new Dictionary<long, int> { [3] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate("Radarr", "Blade Runner 2049", snapshot, profile, ["jpn"], true);

        Assert.False(result.RiskDetected);
        Assert.Empty(result.Warnings);
        Assert.Contains(result.Notes, note => note.Contains("Mystery Format", StringComparison.Ordinal));
        // Unknown specs are not confidently lost, so the score is not reduced for them either.
        Assert.Equal(100, result.PredictedScore);
    }

    [Fact]
    public void A_language_id_this_port_could_not_place_also_cannot_tell()
    {
        var unplaced = new CustomFormatSnapshot(4, "Unplaceable", [new FormatSpecificationSnapshot(RedownloadRiskEvaluator.LanguageImplementation, false, LanguageCode: null, ExceptLanguage: false)]);
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [unplaced], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 60, new Dictionary<long, int> { [4] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate("Radarr", "Blade Runner 2049", snapshot, profile, ["jpn"], true);

        Assert.False(result.RiskDetected);
        Assert.Contains(result.Notes, note => note.Contains("Unplaceable", StringComparison.Ordinal));
    }

    [Fact]
    public void A_format_with_no_language_specification_is_unaffected_by_removed_tracks()
    {
        var resolutionOnly = new CustomFormatSnapshot(5, "2160p Remux", [new FormatSpecificationSnapshot("ResolutionSpecification", false, null, false)]);
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [resolutionOnly], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 60, new Dictionary<long, int> { [5] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate("Radarr", "Blade Runner 2049", snapshot, profile, ["jpn"], true);

        Assert.False(result.RiskDetected);
        Assert.Empty(result.Warnings);
        Assert.Empty(result.Notes);
        Assert.Equal(100, result.PredictedScore);
    }

    [Fact]
    public void Negate_flips_the_languagespecifications_answer_exactly_like_the_source()
    {
        // Sonarr/Radarr LanguageSpecification.IsSatisfiedByWithNegate is the exact negation of
        // IsSatisfiedByWithoutNegate; a negated "except English" spec is satisfied when the file has ONLY
        // English audio, so removing the non-English track makes it satisfied (not lost).
        var negated = new CustomFormatSnapshot(6, "English Only", [new FormatSpecificationSnapshot(RedownloadRiskEvaluator.LanguageImplementation, Negate: true, LanguageCode: "eng", ExceptLanguage: true)]);
        var snapshot = new FileFormatSnapshot(["eng"], [negated], CustomFormatScore: 30);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 20, new Dictionary<long, int> { [6] = 30 });

        // Nothing removed touches the outcome here (the format already only sees English); it must still match.
        var result = RedownloadRiskEvaluator.Evaluate("Sonarr", "Some Show", snapshot, profile, ["ger"], true);

        Assert.False(result.RiskDetected);
        Assert.Empty(result.Warnings);
    }

    [Fact]
    public void Nothing_removed_means_no_risk_without_asking_the_manager_anything()
    {
        var snapshot = new FileFormatSnapshot(["eng", "jpn"], [MultiAudioFormat()], CustomFormatScore: 100);
        var profile = new QualityProfileSnapshot(true, CutoffFormatScore: 60, new Dictionary<long, int> { [1] = 50 });

        var result = RedownloadRiskEvaluator.Evaluate("Radarr", "Blade Runner 2049", snapshot, profile, removedAudioLanguages: [], skipIfManagerWouldRedownload: true);

        Assert.Same(RedownloadRiskAssessment.NoRisk, result);
    }

    [Fact]
    public void Could_not_check_is_a_note_not_a_warning_and_never_recommends_skipping()
    {
        var result = RedownloadRiskAssessment.CouldNotCheck("Radarr");

        Assert.False(result.RiskDetected);
        Assert.False(result.SkipRecommended);
        Assert.Empty(result.Warnings);
        Assert.Single(result.Notes);
    }
}
