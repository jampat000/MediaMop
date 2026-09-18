using Weir.Core.Processing;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Processing;

/// <summary>
/// Issues #495/#497/#498: <see cref="LibraryRules.ApplyRuleSetFields"/> maps the new rule-set input fields onto
/// <see cref="ProcessingRuleSetRecord"/>, and validates the track name template/overrides the same way the engine
/// does (<see cref="TrackNaming.ValidateAll"/>) — an unknown placeholder is refused before anything is stored.
/// </summary>
public sealed class LibraryRulesRuleSetFieldsTests
{
    private static LibraryRules.RuleSetInput ValidInput() => new()
    {
        Name = "Test",
        RemoveHearingImpairedSubs = true,
        AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
        SubtitleMaxPerLanguage = 2,
        SubtitleQualityStrategy = RemuxRuleValues.SubtitleStrategyAccessibility,
        StandardizeTrackNames = true,
        TrackNameTemplate = "{language} {codec}",
        TrackNameOverrides = new TrackNameOverrides
        {
            Forced = "{language} (Forced)",
            HearingImpaired = "{language} (SDH)",
            Commentary = "{language} (Commentary)",
            AudioDescription = "{language} (AD)",
        },
        ClearVideoTrackNames = true,
        RemoveChapters = true,
    };

    [Fact]
    public void Every_new_field_is_mapped_onto_the_record()
    {
        var row = LibraryRules.ApplyRuleSetFields(new ProcessingRuleSetRecord { Name = "Test" }, ValidInput());

        Assert.True(row.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModePerLanguage, row.AudioKeepMode);
        Assert.Equal(2, row.SubtitleMaxPerLanguage);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyAccessibility, row.SubtitleQualityStrategy);
        Assert.True(row.StandardizeTrackNames);
        Assert.Equal("{language} {codec}", row.TrackNameTemplate);
        Assert.Equal("{language} (Forced)", row.TrackNameOverrides.Forced);
        Assert.Equal("{language} (SDH)", row.TrackNameOverrides.HearingImpaired);
        Assert.Equal("{language} (Commentary)", row.TrackNameOverrides.Commentary);
        Assert.Equal("{language} (AD)", row.TrackNameOverrides.AudioDescription);
        Assert.True(row.ClearVideoTrackNames);
        Assert.True(row.RemoveChapters);
    }

    [Fact]
    public void Defaults_match_the_engines_shipped_defaults()
    {
        var row = LibraryRules.ApplyRuleSetFields(new ProcessingRuleSetRecord { Name = "Test" }, new LibraryRules.RuleSetInput { Name = "Test" });

        Assert.False(row.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModeSingle, row.AudioKeepMode);
        Assert.Equal(0, row.SubtitleMaxPerLanguage);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyTextFirst, row.SubtitleQualityStrategy);
        Assert.False(row.StandardizeTrackNames);
        Assert.Equal(TrackNaming.DefaultTemplate, row.TrackNameTemplate);
        Assert.Equal(new TrackNameOverrides(), row.TrackNameOverrides);
        Assert.False(row.ClearVideoTrackNames);
        Assert.False(row.RemoveChapters);
    }

    [Fact]
    public void An_unknown_placeholder_in_the_main_template_is_refused()
    {
        var input = ValidInput() with { TrackNameTemplate = "{language} {bogus}" };

        var exception = Assert.Throws<ProcessingLibraryException>(() =>
            LibraryRules.ApplyRuleSetFields(new ProcessingRuleSetRecord { Name = "Test" }, input));

        Assert.Contains("bogus", exception.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("forced")]
    [InlineData("hearing_impaired")]
    [InlineData("commentary")]
    [InlineData("audio_description")]
    public void An_unknown_placeholder_in_any_override_is_refused(string overrideName)
    {
        var overrides = new TrackNameOverrides();
        overrides = overrideName switch
        {
            "forced" => overrides with { Forced = "{bogus}" },
            "hearing_impaired" => overrides with { HearingImpaired = "{bogus}" },
            "commentary" => overrides with { Commentary = "{bogus}" },
            _ => overrides with { AudioDescription = "{bogus}" },
        };
        var input = ValidInput() with { TrackNameOverrides = overrides };

        var exception = Assert.Throws<ProcessingLibraryException>(() =>
            LibraryRules.ApplyRuleSetFields(new ProcessingRuleSetRecord { Name = "Test" }, input));

        Assert.Contains("bogus", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_default_template_and_overrides_never_throw() =>
        LibraryRules.ApplyRuleSetFields(new ProcessingRuleSetRecord { Name = "Test" }, new LibraryRules.RuleSetInput { Name = "Test" });
}
