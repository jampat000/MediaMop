using Weir.Core.Processing;
using Weir.Core.Rules;
using Weir.Infrastructure.Processing.RemuxPass;

namespace Weir.Infrastructure.Tests.Processing.RemuxPass;

/// <summary>
/// Issues #495/#497/#498: both config-building paths (<see cref="RuleSetConversion.ToRulesConfig"/>, the
/// rule-less/seeded-library fallback, and <see cref="RemuxPassPaths.RulesConfigFor"/>, the path a real pass
/// and the #502 preview take) must map the new rule-set fields onto <see cref="ProcessingRulesConfig"/> the same
/// way, matching the existing "both paths agree" guarantee <c>SubtitleModeNormalizationTests</c> already
/// proves for <c>SubtitleMode</c>.
/// </summary>
public sealed class RuleSetFieldsMappingTests
{
    private static ProcessingRuleSetRecord RuleSet() => new()
    {
        Name = "Test",
        RemoveHearingImpairedSubs = true,
        AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
        SubtitleMaxPerLanguage = 2,
        SubtitleQualityStrategy = RemuxRuleValues.SubtitleStrategyAccessibility,
        StandardizeTrackNames = true,
        TrackNameTemplate = "{language} {codec}",
        TrackNameOverrides = new TrackNameOverrides { Forced = "{language} (Forced)" },
        ClearVideoTrackNames = true,
        RemoveChapters = true,
    };

    [Fact]
    public void RulesConfigFor_maps_every_new_field()
    {
        var config = RemuxPassPaths.RulesConfigFor(RuleSet());

        Assert.True(config.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModePerLanguage, config.AudioKeepMode);
        Assert.Equal(2, config.SubtitleMaxPerLanguage);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyAccessibility, config.SubtitleQualityStrategy);
        Assert.True(config.Metadata.StandardizeTrackNames);
        Assert.Equal("{language} {codec}", config.Metadata.TrackNameTemplate);
        Assert.Equal("{language} (Forced)", config.Metadata.TrackNameOverrides.Forced);
        Assert.True(config.Metadata.ClearVideoTrackNames);
        Assert.True(config.Metadata.RemoveChapters);
    }

    [Fact]
    public void ToRulesConfig_maps_every_new_field_the_same_way()
    {
        var live = RemuxPassPaths.RulesConfigFor(RuleSet());
        var fallback = RuleSetConversion.ToRulesConfig(RuleSet());

        Assert.Equal(live.RemoveHearingImpairedSubs, fallback.RemoveHearingImpairedSubs);
        Assert.Equal(live.AudioKeepMode, fallback.AudioKeepMode);
        Assert.Equal(live.SubtitleMaxPerLanguage, fallback.SubtitleMaxPerLanguage);
        Assert.Equal(live.SubtitleQualityStrategy, fallback.SubtitleQualityStrategy);
        Assert.Equal(live.Metadata, fallback.Metadata);
    }

    [Fact]
    public void A_missing_rule_set_yields_engine_defaults_for_every_new_field()
    {
        var config = RuleSetConversion.ToRulesConfig(null);

        Assert.False(config.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModeSingle, config.AudioKeepMode);
        Assert.Equal(0, config.SubtitleMaxPerLanguage);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyTextFirst, config.SubtitleQualityStrategy);
        Assert.False(config.Metadata.StandardizeTrackNames);
        Assert.False(config.Metadata.ClearVideoTrackNames);
        Assert.False(config.Metadata.RemoveChapters);
    }

    [Theory]
    [InlineData("bogus", RemuxRuleValues.AudioKeepModeSingle)]
    [InlineData("per_language", RemuxRuleValues.AudioKeepModePerLanguage)]
    [InlineData("", RemuxRuleValues.AudioKeepModeSingle)]
    public void Unknown_stored_audio_keep_mode_normalizes_to_single(string stored, string expected)
    {
        var ruleSet = RuleSet() with { AudioKeepMode = stored };

        Assert.Equal(expected, RemuxPassPaths.RulesConfigFor(ruleSet).AudioKeepMode);
        Assert.Equal(expected, RuleSetConversion.ToRulesConfig(ruleSet).AudioKeepMode);
    }

    [Theory]
    [InlineData("bogus", RemuxRuleValues.SubtitleStrategyTextFirst)]
    [InlineData("image_first", RemuxRuleValues.SubtitleStrategyImageFirst)]
    [InlineData("accessibility", RemuxRuleValues.SubtitleStrategyAccessibility)]
    public void Unknown_stored_subtitle_strategy_normalizes_to_text_first(string stored, string expected)
    {
        var ruleSet = RuleSet() with { SubtitleQualityStrategy = stored };

        Assert.Equal(expected, RemuxPassPaths.RulesConfigFor(ruleSet).SubtitleQualityStrategy);
        Assert.Equal(expected, RuleSetConversion.ToRulesConfig(ruleSet).SubtitleQualityStrategy);
    }
}
