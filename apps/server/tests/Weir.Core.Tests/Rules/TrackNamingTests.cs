using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// The #498 track-name template engine: placeholder rendering, override selection and validation. This is a new
/// .NET-only feature (the Python reference has no equivalent yet, per issue #498), so these are ordinary
/// hand-written expectations rather than golden fixtures generated from Python.
/// </summary>
public sealed class TrackNamingTests
{
    private static TrackNameContext Context(
        string language = "English",
        string? variant = null,
        int channels = 6,
        string codec = "truehd",
        TrackFlags? flags = null) => new()
    {
        Language = language,
        Variant = variant,
        Channels = channels,
        CodecName = codec,
        Flags = flags ?? new TrackFlags(),
    };

    // --- placeholders -------------------------------------------------------------------

    [Fact]
    public void Language_renders_verbatim() => Assert.Equal("English", TrackNaming.Render("{language}", Context()));

    [Fact]
    public void Variant_is_empty_when_the_track_has_none() => Assert.Equal(string.Empty, TrackNaming.Render("{variant}", Context(variant: null)));

    [Fact]
    public void Variant_is_parenthesized_when_present() => Assert.Equal("(VFQ)", TrackNaming.Render("{variant}", Context(variant: "VFQ")));

    [Fact]
    public void Channels_reuses_the_display_helper() =>
        Assert.Equal(RemuxDisplay.ChannelsDisplay(2), TrackNaming.Render("{channels}", Context(channels: 2)));

    [Fact]
    public void Codec_reuses_the_display_helper() =>
        Assert.Equal(RemuxDisplay.CodecDisplayName("eac3"), TrackNaming.Render("{codec}", Context(codec: "eac3")));

    [Fact]
    public void Flags_is_empty_when_no_flag_is_set() => Assert.Equal(string.Empty, TrackNaming.Render("{flags}", Context()));

    [Fact]
    public void Flags_lists_every_active_flag_in_a_fixed_order()
    {
        var flags = new TrackFlags { AudioDescription = true, Forced = true, Commentary = true, HearingImpaired = true };

        Assert.Equal("Forced, Hearing Impaired, Commentary, Audio Description", TrackNaming.Render("{flags}", Context(flags: flags)));
    }

    // --- the default template ------------------------------------------------------------

    [Fact]
    public void The_default_template_has_no_gap_when_there_is_no_variant() =>
        Assert.Equal("English 5.1 TrueHD", TrackNaming.Render(TrackNaming.DefaultTemplate, Context()));

    [Fact]
    public void The_default_template_adds_a_parenthesized_variant_when_present() =>
        Assert.Equal("English (VFQ) 5.1 TrueHD", TrackNaming.Render(TrackNaming.DefaultTemplate, Context(variant: "VFQ")));

    [Fact]
    public void A_subtitle_with_no_channels_or_codec_renders_just_the_language() =>
        Assert.Equal("French", TrackNaming.Render(TrackNaming.DefaultTemplate, Context(language: "French", channels: 0, codec: string.Empty)));

    // --- unknown placeholders --------------------------------------------------------------

    [Fact]
    public void A_template_of_only_known_placeholders_validates_without_throwing()
    {
        var exception = Record.Exception(() => TrackNaming.ValidateTemplate(TrackNaming.DefaultTemplate));

        Assert.Null(exception);
    }

    [Fact]
    public void An_unknown_placeholder_is_rejected_with_a_clear_message()
    {
        var error = Assert.Throws<TrackNameTemplateException>(() => TrackNaming.ValidateTemplate("{language} {bogus}"));

        Assert.Contains("{bogus}", error.Message, StringComparison.Ordinal);
        Assert.Contains("{language}", error.Message, StringComparison.Ordinal);
        Assert.Contains("{flags}", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Rendering_an_unknown_placeholder_also_throws() =>
        Assert.Throws<TrackNameTemplateException>(() => TrackNaming.Render("{nope}", Context()));

    [Fact]
    public void ValidateAll_checks_the_main_template_and_every_override()
    {
        var rules = new MetadataRules { TrackNameOverrides = new TrackNameOverrides { Commentary = "{language} {nope}" } };

        var error = Assert.Throws<TrackNameTemplateException>(() => TrackNaming.ValidateAll(rules));

        Assert.Contains("{nope}", error.Message, StringComparison.Ordinal);
    }

    // --- override resolution --------------------------------------------------------------

    [Fact]
    public void No_flags_fall_back_to_the_main_template()
    {
        var rules = new MetadataRules { TrackNameTemplate = "{language}" };

        Assert.Equal("{language}", TrackNaming.ResolveTemplate(rules, new TrackFlags()));
    }

    [Fact]
    public void Forced_takes_priority_over_every_other_flag()
    {
        var rules = new MetadataRules();
        var flags = new TrackFlags { Forced = true, HearingImpaired = true, Commentary = true, AudioDescription = true };

        Assert.Equal(rules.TrackNameOverrides.Forced, TrackNaming.ResolveTemplate(rules, flags));
    }

    [Fact]
    public void HearingImpaired_is_used_when_forced_is_not_set()
    {
        var rules = new MetadataRules();
        var flags = new TrackFlags { HearingImpaired = true, Commentary = true, AudioDescription = true };

        Assert.Equal(rules.TrackNameOverrides.HearingImpaired, TrackNaming.ResolveTemplate(rules, flags));
    }

    [Fact]
    public void Commentary_is_used_when_forced_and_hearing_impaired_are_not_set()
    {
        var rules = new MetadataRules();
        var flags = new TrackFlags { Commentary = true, AudioDescription = true };

        Assert.Equal(rules.TrackNameOverrides.Commentary, TrackNaming.ResolveTemplate(rules, flags));
    }

    [Fact]
    public void AudioDescription_is_used_only_when_nothing_else_matches()
    {
        var rules = new MetadataRules();

        Assert.Equal(rules.TrackNameOverrides.AudioDescription, TrackNaming.ResolveTemplate(rules, new TrackFlags { AudioDescription = true }));
    }

    [Fact]
    public void Clearing_an_override_to_empty_falls_back_to_the_main_template()
    {
        var rules = new MetadataRules { TrackNameOverrides = new TrackNameOverrides { Forced = string.Empty } };

        Assert.Equal(rules.TrackNameTemplate, TrackNaming.ResolveTemplate(rules, new TrackFlags { Forced = true }));
    }

    [Fact]
    public void The_default_forced_override_reads_language_then_forced()
    {
        var rules = new MetadataRules();
        var flags = new TrackFlags { Forced = true };

        var rendered = TrackNaming.Render(TrackNaming.ResolveTemplate(rules, flags), Context(flags: flags));

        Assert.Equal("English Forced", rendered);
    }

    // --- PlannedTrack integration -----------------------------------------------------------

    [Fact]
    public void RenderTrackName_reads_language_channels_and_codec_from_the_planned_track()
    {
        var track = new PlannedTrack { InputIndex = 0, LangLabel = "eng", Channels = 6, CodecName = "eac3" };

        Assert.Equal("English 5.1 E-AC-3", TrackNaming.RenderTrackName(new MetadataRules(), track));
    }

    [Fact]
    public void RenderTrackName_uses_the_forced_override_for_a_forced_planned_track()
    {
        var track = new PlannedTrack { InputIndex = 0, LangLabel = "eng", Forced = true };

        Assert.Equal("English Forced", TrackNaming.RenderTrackName(new MetadataRules(), track));
    }

    [Fact]
    public void RenderTrackName_uses_the_commentary_override_for_a_commentary_planned_track()
    {
        var track = new PlannedTrack { InputIndex = 0, LangLabel = "eng", Commentary = true };

        Assert.Equal("English Commentary", TrackNaming.RenderTrackName(new MetadataRules(), track));
    }

    [Fact]
    public void ContextFor_never_sets_a_variant_in_this_branch()
    {
        var track = new PlannedTrack { InputIndex = 0, LangLabel = "eng" };

        Assert.Null(TrackNaming.ContextFor(track).Variant);
    }
}
