using Weir.Core.Refiner;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Refiner;

/// <summary>
/// Issues #495/#497/#498's storage: <see cref="RuleSetRuleExtras"/> packs their new rule-set fields into the
/// existing <c>subtitle_sorters_json</c> column (ADR-0017 freezes the schema until the switch-over). These
/// tests prove the encode/decode round trip and, most importantly, that every shape the column held before
/// this change (empty, or a bare sorter array) still decodes to the shipped defaults for every new field.
/// </summary>
public sealed class RuleSetRuleExtrasTests
{
    [Fact]
    public void An_empty_column_decodes_to_every_default()
    {
        var decoded = RuleSetRuleExtras.Decode("");

        Assert.Equal(string.Empty, decoded.SubtitleSortersJson);
        Assert.False(decoded.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModeSingle, decoded.AudioKeepMode);
        Assert.Equal(0, decoded.SubtitleMaxPerLanguage);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyTextFirst, decoded.SubtitleQualityStrategy);
        Assert.False(decoded.StandardizeTrackNames);
        Assert.Equal(TrackNaming.DefaultTemplate, decoded.TrackNameTemplate);
        Assert.Equal(new TrackNameOverrides(), decoded.TrackNameOverrides);
        Assert.False(decoded.ClearVideoTrackNames);
        Assert.False(decoded.RemoveChapters);
    }

    [Fact]
    public void A_null_column_decodes_the_same_as_empty() =>
        Assert.Equal(RuleSetRuleExtras.Decode(""), RuleSetRuleExtras.Decode(null));

    [Fact]
    public void A_legacy_bare_sorter_array_is_kept_verbatim_with_default_extras()
    {
        const string legacy = """[{"field":"forced","value":null,"reversed":false}]""";

        var decoded = RuleSetRuleExtras.Decode(legacy);

        Assert.Equal(legacy, decoded.SubtitleSortersJson);
        Assert.False(decoded.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModeSingle, decoded.AudioKeepMode);
    }

    [Fact]
    public void Garbage_text_is_kept_as_the_sorter_list_with_default_extras()
    {
        var decoded = RuleSetRuleExtras.Decode("not json at all");

        Assert.Equal("not json at all", decoded.SubtitleSortersJson);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyTextFirst, decoded.SubtitleQualityStrategy);
    }

    [Fact]
    public void Encode_then_decode_round_trips_every_field()
    {
        var value = new RuleSetRuleExtras.Decoded
        {
            SubtitleSortersJson = TrackSorters.Dump(TrackSorters.DefaultSubtitleSorters),
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

        var encoded = RuleSetRuleExtras.Encode(value);
        var decoded = RuleSetRuleExtras.Decode(encoded);

        Assert.Equal(value.SubtitleSortersJson, decoded.SubtitleSortersJson);
        Assert.Equal(value.RemoveHearingImpairedSubs, decoded.RemoveHearingImpairedSubs);
        Assert.Equal(value.AudioKeepMode, decoded.AudioKeepMode);
        Assert.Equal(value.SubtitleMaxPerLanguage, decoded.SubtitleMaxPerLanguage);
        Assert.Equal(value.SubtitleQualityStrategy, decoded.SubtitleQualityStrategy);
        Assert.Equal(value.StandardizeTrackNames, decoded.StandardizeTrackNames);
        Assert.Equal(value.TrackNameTemplate, decoded.TrackNameTemplate);
        Assert.Equal(value.TrackNameOverrides, decoded.TrackNameOverrides);
        Assert.Equal(value.ClearVideoTrackNames, decoded.ClearVideoTrackNames);
        Assert.Equal(value.RemoveChapters, decoded.RemoveChapters);
    }

    [Fact]
    public void Encode_with_an_empty_sorter_list_writes_a_null_sorters_key_and_decodes_back_to_empty()
    {
        var encoded = RuleSetRuleExtras.Encode(new RuleSetRuleExtras.Decoded { SubtitleSortersJson = "" });

        Assert.Contains("\"sorters\":null", encoded, StringComparison.Ordinal);
        Assert.Equal(string.Empty, RuleSetRuleExtras.Decode(encoded).SubtitleSortersJson);
    }

    [Fact]
    public void An_object_with_no_rule_extras_key_decodes_its_sorters_with_default_extras()
    {
        const string stored = """{"sorters":[{"field":"language","value":null,"reversed":false}]}""";

        var decoded = RuleSetRuleExtras.Decode(stored);

        Assert.Equal("""[{"field":"language","value":null,"reversed":false}]""", decoded.SubtitleSortersJson);
        Assert.False(decoded.RemoveHearingImpairedSubs);
    }

    [Fact]
    public void Extras_missing_individual_fields_default_only_those_fields()
    {
        const string stored = """{"sorters":null,"rule_extras_v1":{"remove_hearing_impaired_subs":true}}""";

        var decoded = RuleSetRuleExtras.Decode(stored);

        Assert.True(decoded.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModeSingle, decoded.AudioKeepMode);
        Assert.Equal(TrackNaming.DefaultTemplate, decoded.TrackNameTemplate);
        Assert.Equal(new TrackNameOverrides(), decoded.TrackNameOverrides);
    }

    [Fact]
    public void Track_name_overrides_missing_individual_flags_default_only_those_flags()
    {
        const string stored = """{"sorters":null,"rule_extras_v1":{"track_name_overrides":{"forced":"{language} FORCED"}}}""";

        var decoded = RuleSetRuleExtras.Decode(stored);

        Assert.Equal("{language} FORCED", decoded.TrackNameOverrides.Forced);
        Assert.Equal(new TrackNameOverrides().HearingImpaired, decoded.TrackNameOverrides.HearingImpaired);
    }
}
