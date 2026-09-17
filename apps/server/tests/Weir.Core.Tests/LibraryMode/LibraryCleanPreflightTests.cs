using Weir.Core.LibraryMode;

namespace Weir.Core.Tests.LibraryMode;

public sealed class LibraryCleanPreflightTests
{
    private const string Path = "/library/Movie (2020)/Movie (2020).mkv";

    [Fact]
    public void A_clean_file_with_no_risk_is_not_skipped()
    {
        var result = LibraryCleanPreflight.Evaluate(Path, HardlinkDecision.Allow, RedownloadRiskAssessment.NoRisk);

        Assert.False(result.Skip);
        Assert.Empty(result.SkipReasons);
        Assert.Empty(result.RedownloadWarnings);
        Assert.Empty(result.Notes);
    }

    [Fact]
    public void A_seeding_file_is_skipped_with_the_hardlink_reason()
    {
        var hardlink = new HardlinkDecision(Skip: true, Reason: HardlinkPolicy.SeedingReason);

        var result = LibraryCleanPreflight.Evaluate(Path, hardlink, RedownloadRiskAssessment.NoRisk);

        Assert.True(result.Skip);
        Assert.Equal(["still shared with a download (seeding)"], result.SkipReasons);
    }

    [Fact]
    public void A_redownload_risk_that_recommends_skipping_adds_its_message_as_a_skip_reason()
    {
        var risk = new RedownloadRiskAssessment
        {
            RiskDetected = true,
            SkipRecommended = true,
            Warnings = [new RedownloadRiskWarning("Radarr", "Blade Runner 2049", "Multi-Audio", 50)],
        };

        var result = LibraryCleanPreflight.Evaluate(Path, HardlinkDecision.Allow, risk);

        Assert.True(result.Skip);
        Assert.Equal(["Radarr may download Blade Runner 2049 again: its 'Multi-Audio' format (+50) would no longer match."], result.SkipReasons);
        Assert.Single(result.RedownloadWarnings);
    }

    [Fact]
    public void A_redownload_warning_shows_even_when_it_did_not_cause_a_skip()
    {
        // skip_if_manager_would_redownload can be off: the warning should still reach the confirmation dialog.
        var risk = new RedownloadRiskAssessment
        {
            RiskDetected = true,
            SkipRecommended = false,
            Warnings = [new RedownloadRiskWarning("Radarr", "Blade Runner 2049", "Multi-Audio", 50)],
        };

        var result = LibraryCleanPreflight.Evaluate(Path, HardlinkDecision.Allow, risk);

        Assert.False(result.Skip);
        Assert.Empty(result.SkipReasons);
        Assert.Single(result.RedownloadWarnings);
    }

    [Fact]
    public void Both_reasons_can_apply_to_the_same_file()
    {
        var hardlink = new HardlinkDecision(true, HardlinkPolicy.SeedingReason);
        var risk = new RedownloadRiskAssessment
        {
            RiskDetected = true,
            SkipRecommended = true,
            Warnings = [new RedownloadRiskWarning("Sonarr", "Some Show", "Japanese Audio", 40)],
        };

        var result = LibraryCleanPreflight.Evaluate(Path, hardlink, risk);

        Assert.True(result.Skip);
        Assert.Equal(2, result.SkipReasons.Count);
    }

    [Fact]
    public void A_null_redownload_assessment_is_treated_as_no_risk()
    {
        var result = LibraryCleanPreflight.Evaluate(Path, HardlinkDecision.Allow, redownloadRisk: null);

        Assert.False(result.Skip);
        Assert.Empty(result.RedownloadWarnings);
    }

    [Fact]
    public void Notes_from_the_risk_assessment_pass_through_untouched()
    {
        var risk = RedownloadRiskAssessment.CouldNotCheck("Radarr");

        var result = LibraryCleanPreflight.Evaluate(Path, HardlinkDecision.Allow, risk);

        Assert.False(result.Skip);
        Assert.Single(result.Notes);
    }
}
