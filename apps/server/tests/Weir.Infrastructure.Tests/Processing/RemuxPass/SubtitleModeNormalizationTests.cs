using Weir.Core.Processing;
using Weir.Core.Rules;
using Weir.Infrastructure.Processing.RemuxPass;

namespace Weir.Infrastructure.Tests.Processing.RemuxPass;

/// <summary>
/// Issue #545 item 4: <c>rules_config_for</c> (the path a live remux job takes) used to pass the stored subtitle mode
/// through unchanged, while the fallback path (<see cref="RuleSetConversion.ToRulesConfig"/>, used when a library has
/// no rule set of its own) normalized it. A library saved with the shipped default, <c>keep_all</c>, is not one of the
/// two modes the planner implements (<see cref="RemuxRuleValues.SubtitleModeRemoveAll"/> or
/// <see cref="RemuxRuleValues.SubtitleModeKeepSelected"/>), so both paths must agree on the same normalization.
/// </summary>
public sealed class SubtitleModeNormalizationTests
{
    private static ProcessingRuleSetRecord RuleSet(string subtitleMode) => new() { Name = "Test", SubtitleMode = subtitleMode };

    [Theory]
    [InlineData("keep_all", RemuxRuleValues.SubtitleModeKeepSelected)]
    [InlineData("", RemuxRuleValues.SubtitleModeKeepSelected)]
    [InlineData("bogus", RemuxRuleValues.SubtitleModeKeepSelected)]
    [InlineData("remove_all", RemuxRuleValues.SubtitleModeRemoveAll)]
    [InlineData("REMOVE_ALL", RemuxRuleValues.SubtitleModeRemoveAll)]
    [InlineData(" remove_all ", RemuxRuleValues.SubtitleModeRemoveAll)]
    public void Both_config_paths_normalize_the_stored_mode_the_same_way(string stored, string expected)
    {
        var ruleSet = RuleSet(stored);

        var live = RemuxPassPaths.RulesConfigFor(ruleSet);
        var fallback = RuleSetConversion.ToRulesConfig(ruleSet);

        Assert.Equal(expected, live.SubtitleMode);
        Assert.Equal(expected, fallback.SubtitleMode);
        Assert.Equal(fallback.SubtitleMode, live.SubtitleMode);
    }
}
