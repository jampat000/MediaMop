using System.Text.Json;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Issue #495: hearing-impaired, forced/signs, dub, audio-description and commentary detection
/// from a track's name, backed up by (never overridden by) its ffprobe disposition flag.
/// </summary>
public sealed class TrackFlagsTests
{
    private static ProbeStreamInfo SubtitleWithTitle(string title, string disposition = "{}") =>
        ProbeStreamInfo.Parse($$"""{"index": 0, "codec_type": "subtitle", "tags": {"title": {{JsonSerializer.Serialize(title)}}}, "disposition": {{disposition}}}""");

    // --- the name -> flags table, including the issue's own false positives ---------------

    [Theory]
    // Hearing-impaired: whole-word abbreviations and multi-word keywords.
    [InlineData("English (SDH)", true, false, false, false, false)]
    [InlineData("English [CC]", true, false, false, false, false)]
    [InlineData("English (HI)", true, false, false, false, false)]
    [InlineData("HOH", true, false, false, false, false)]
    [InlineData("SHD", true, false, false, false, false)]
    [InlineData("Closed Caption", true, false, false, false, false)]
    [InlineData("Hearing Impaired", true, false, false, false, false)]
    [InlineData("English for Deaf viewers", true, false, false, false, false)]
    // Forced / signs.
    [InlineData("Forced", false, true, false, false, false)]
    [InlineData("Foreign Parts Only", false, true, false, false, false)]
    [InlineData("Signs", false, true, false, false, false)]
    [InlineData("Signs & Songs", false, true, false, false, false)]
    // Dub, whole word only.
    [InlineData("German Dubbed", false, false, true, false, false)]
    [InlineData("Dub", false, false, true, false, false)]
    [InlineData("Dubtitle", false, false, true, false, false)]
    // Audio description.
    [InlineData("Descriptive Audio", false, false, false, true, false)]
    [InlineData("Audio Description", false, false, false, true, false)]
    // Commentary.
    [InlineData("Director's Commentary", false, false, false, false, true)]
    // The issue's own false positives: a short abbreviation must match only as a whole word.
    [InlineData("Accessibility", false, false, false, false, false)]
    [InlineData("This", false, false, false, false, false)]
    [InlineData("Design", false, false, false, false, false)]
    [InlineData("Dubai", false, false, false, false, false)]
    // An ordinary name with none of the keywords.
    [InlineData("English", false, false, false, false, false)]
    public void Names_map_to_the_documented_flags(string title, bool hearingImpaired, bool forced, bool dub, bool audioDescription, bool commentary)
    {
        var flags = TrackFlagsReader.Detect(SubtitleWithTitle(title));

        Assert.Equal(hearingImpaired, flags.HearingImpaired.Value);
        Assert.Equal(forced, flags.Forced.Value);
        Assert.Equal(dub, flags.Dub.Value);
        Assert.Equal(audioDescription, flags.AudioDescription.Value);
        Assert.Equal(commentary, flags.Commentary.Value);
    }

    // --- disposition wins, and provenance is reported correctly ---------------------------

    [Fact]
    public void A_disposition_flag_is_reported_as_coming_from_the_disposition()
    {
        var stream = SubtitleWithTitle("Plain English", """{"hearing_impaired": 1}""");

        var flags = TrackFlagsReader.Detect(stream);

        Assert.True(flags.HearingImpaired.Value);
        Assert.Equal(TrackFlagSource.Disposition, flags.HearingImpaired.Source);
        Assert.True(flags.HearingImpaired.FromDisposition);
        Assert.False(flags.HearingImpaired.FromName);
    }

    [Fact]
    public void A_name_only_match_is_reported_as_coming_from_the_name()
    {
        var stream = SubtitleWithTitle("English (SDH)");

        var flags = TrackFlagsReader.Detect(stream);

        Assert.True(flags.HearingImpaired.Value);
        Assert.Equal(TrackFlagSource.Name, flags.HearingImpaired.Source);
        Assert.True(flags.HearingImpaired.FromName);
    }

    [Fact]
    public void A_disposition_flag_set_with_a_name_that_says_nothing_still_wins()
    {
        // The disposition is checked first regardless of what the name does or does not say.
        var stream = SubtitleWithTitle("English", """{"forced": 1}""");

        var flags = TrackFlagsReader.Detect(stream);

        Assert.True(flags.Forced.Value);
        Assert.Equal(TrackFlagSource.Disposition, flags.Forced.Source);
    }

    // --- wired into subtitle planning: forced/signs and hearing-impaired removal -----------

    private static ProbeStreamInfo Video => ProbeStreamInfo.Parse("""{"index": 0, "codec_type": "video", "codec_name": "h264"}""");

    private static ProbeStreamInfo EnglishAudio => ProbeStreamInfo.Parse(
        """{"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");

    [Fact]
    public void An_SDH_subtitle_track_is_removed_only_when_the_rule_is_enabled()
    {
        var sdh = ProbeStreamInfo.Parse("""{"index": 2, "codec_type": "subtitle", "tags": {"language": "eng", "title": "English (SDH)"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["eng"] };

        var withRuleOff = RemuxRules.PlanRemux([Video], [EnglishAudio], [sdh], config);
        Assert.NotNull(withRuleOff);
        Assert.Single(withRuleOff!.Subtitles);

        var withRuleOn = RemuxRules.PlanRemux([Video], [EnglishAudio], [sdh], config with { RemoveHearingImpairedSubs = true });
        Assert.NotNull(withRuleOn);
        Assert.Empty(withRuleOn!.Subtitles);
        Assert.Contains("eng", withRuleOn.RemovedSubtitles);
        Assert.Contains(withRuleOn.AudioSelectionNotes, n => n.Contains("hearing-impaired", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void An_unflagged_signs_track_counts_as_forced_under_preserve_forced()
    {
        var signs = ProbeStreamInfo.Parse(
            """{"index": 2, "codec_type": "subtitle", "tags": {"language": "eng", "title": "Signs & Songs"}, "disposition": {"forced": 0}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng"],
            PreserveForcedSubs = true,
        };

        var plan = RemuxRules.PlanRemux([Video], [EnglishAudio], [signs], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Subtitles);
        Assert.True(plan.Subtitles[0].Forced);
        Assert.Contains(plan.AudioSelectionNotes, n => n.Contains("counts as forced", StringComparison.Ordinal));
    }

    [Fact]
    public void An_unflagged_ordinary_subtitle_is_not_forced()
    {
        var ordinary = ProbeStreamInfo.Parse(
            """{"index": 2, "codec_type": "subtitle", "tags": {"language": "eng", "title": "English"}, "disposition": {"forced": 0}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["eng"] };

        var plan = RemuxRules.PlanRemux([Video], [EnglishAudio], [ordinary], config);

        Assert.NotNull(plan);
        Assert.False(plan!.Subtitles[0].Forced);
    }

    // --- wired into audio candidate building: a name-only flag is called out --------------

    [Fact]
    public void A_selected_track_flagged_only_by_its_name_says_so_in_the_notes()
    {
        var dubbed = ProbeStreamInfo.Parse(
            """{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "eng", "title": "German Dubbed"}}""");

        var plan = RemuxRules.PlanRemux([Video], [dubbed], [], RemuxRules.DefaultConfig());

        Assert.NotNull(plan);
        Assert.Contains(plan!.AudioSelectionNotes, n => n.Contains("looks like a dub track", StringComparison.Ordinal) && n.Contains("its name", StringComparison.Ordinal));
    }
}
