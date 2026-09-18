using Weir.Core.Rules;

namespace Weir.Core.Processing;

/// <summary>
/// Convert a stored rule set into the config the remux planner takes (port of
/// <c>processing_remux_rules_settings_service.rule_set_to_rules_config</c>). Deliberately the simpler of the
/// two Python conversions: the ADR-0014 module docstring notes its HTTP view was removed in #460 and only
/// the conversion itself, plus the rule-less fallback, remain.
/// </summary>
public static class RuleSetConversion
{
    /// <summary>
    /// The planner's own reading of a stored subtitle mode (<c>_normalize_subtitle_mode</c>). The stored
    /// server default is <c>keep_all</c>, which is not one of the two modes the planner implements; it
    /// asks only whether the value is <c>remove_all</c> and treats everything else as keep-selected.
    /// </summary>
    public static string NormalizeSubtitleMode(string? raw) =>
        string.Equals((raw ?? string.Empty).Trim(), RemuxRuleValues.SubtitleModeRemoveAll, StringComparison.OrdinalIgnoreCase)
            ? RemuxRuleValues.SubtitleModeRemoveAll
            : RemuxRuleValues.SubtitleModeKeepSelected;

    /// <summary>One rule set as the config the planner takes. A missing rule set yields the shipped defaults.</summary>
    public static ProcessingRulesConfig ToRulesConfig(ProcessingRuleSetRecord? row)
    {
        if (row is null)
        {
            return RemuxRules.DefaultConfig();
        }

        return new ProcessingRulesConfig
        {
            PrimaryAudioLang = row.PrimaryAudioLang,
            SecondaryAudioLang = row.SecondaryAudioLang,
            TertiaryAudioLang = row.TertiaryAudioLang,
            DefaultAudioSlot = row.DefaultAudioSlot,
            RemoveCommentary = row.RemoveCommentary,
            SubtitleMode = NormalizeSubtitleMode(row.SubtitleMode),
            SubtitleLangs = [.. (row.SubtitleLangsCsv ?? string.Empty).Split(',').Select(x => x.Trim()).Where(x => x.Length > 0)],
            PreserveForcedSubs = row.PreserveForcedSubs,
            PreserveDefaultSubs = row.PreserveDefaultSubs,
            AudioPreferenceMode = RemuxRules.NormalizeAudioPreferenceMode(row.AudioPreferenceMode),
            AudioSortersJson = row.AudioSortersJson ?? string.Empty,
            RemoveHearingImpairedSubs = row.RemoveHearingImpairedSubs,
            AudioKeepMode = RemuxRules.NormalizeAudioKeepMode(row.AudioKeepMode),
            SubtitleMaxPerLanguage = row.SubtitleMaxPerLanguage,
            SubtitleQualityStrategy = RemuxRules.NormalizeSubtitleQualityStrategy(row.SubtitleQualityStrategy),
            Metadata = new MetadataRules
            {
                RemoveImages = row.RemoveImages,
                RemoveAttachments = row.RemoveAttachments,
                RemoveTitle = row.RemoveTitle,
                RemoveLanguageTags = row.RemoveLanguageTags,
                RemoveOtherMetadata = row.RemoveOtherMetadata,
                StandardizeTrackNames = row.StandardizeTrackNames,
                TrackNameTemplate = row.TrackNameTemplate,
                TrackNameOverrides = row.TrackNameOverrides,
                ClearVideoTrackNames = row.ClearVideoTrackNames,
                RemoveChapters = row.RemoveChapters,
            },
        };
    }
}
