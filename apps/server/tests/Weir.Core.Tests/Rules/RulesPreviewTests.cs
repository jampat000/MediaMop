using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Issue #502's per-track preview rows: built from the exact same <see cref="RemuxPlan"/> a live pass
/// would compute for the same probe and rules, so every reason a row carries is a sentence
/// <see cref="RemuxRules.PlanRemux"/> itself wrote — never a re-derived guess.
/// </summary>
public sealed class RulesPreviewTests
{
    private const string Fixture = """
        {
          "format": {"duration": "120.0"},
          "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000",
             "tags": {"language": "eng"}, "disposition": {"default": 1}},
            {"index": 2, "codec_type": "audio", "codec_name": "dts", "channels": 6, "bit_rate": "1500000",
             "tags": {"language": "jpn"}},
            {"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
            {"index": 4, "codec_type": "subtitle", "codec_name": "subrip", "bit_rate": "1000", "tags": {"language": "spa"}}
          ]
        }
        """;

    private static (ProbeResult Probe, RemuxPlan Plan) Plan()
    {
        var probe = ProbeResult.Parse(Fixture);
        var (video, audio, subtitles) = RemuxRules.SplitStreams(probe);
        var config = RemuxRules.DefaultConfig() with
        {
            PrimaryAudioLang = "eng",
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng"],
        };
        var plan = RemuxRules.PlanRemux(video, audio, subtitles, config);
        Assert.NotNull(plan);
        return (probe, plan!);
    }

    [Fact]
    public void One_row_per_video_audio_and_subtitle_stream_in_index_order()
    {
        var (probe, plan) = Plan();

        var rows = RulesPreview.BuildTrackRows(probe, plan);

        Assert.Equal([0, 1, 2, 3, 4], rows.Select(r => r.Index));
        Assert.Equal(["video", "audio", "audio", "subtitle", "subtitle"], rows.Select(r => r.Type));
    }

    [Fact]
    public void The_video_track_is_always_kept_here_and_carries_no_stream_specific_note()
    {
        var (probe, plan) = Plan();

        var video = RulesPreview.BuildTrackRows(probe, plan).Single(r => r.Index == 0);

        Assert.True(video.Kept);
        Assert.Equal("Video track kept unchanged.", Assert.Single(video.Reasons));
    }

    [Fact]
    public void The_winning_audio_track_is_kept_and_its_reasons_are_verbatim_plan_notes()
    {
        var (probe, plan) = Plan();

        var winner = RulesPreview.BuildTrackRows(probe, plan).Single(r => r.Index == 1);

        Assert.True(winner.Kept);
        Assert.True(winner.Default);
        Assert.NotEmpty(winner.Reasons);
        Assert.All(winner.Reasons, reason => Assert.Contains(reason, plan.AudioSelectionNotes));
        Assert.Contains(winner.Reasons, r => r.Contains("as the only track in the first matching language tier", StringComparison.Ordinal));
        Assert.Contains(winner.Reasons, r => r.Contains("Removed non-selected", StringComparison.Ordinal));
    }

    [Fact]
    public void The_losing_audio_track_is_dropped_and_shares_the_removal_note_with_the_winner()
    {
        var (probe, plan) = Plan();

        var loser = RulesPreview.BuildTrackRows(probe, plan).Single(r => r.Index == 2);

        Assert.False(loser.Kept);
        Assert.All(loser.Reasons, reason => Assert.Contains(reason, plan.AudioSelectionNotes));
        Assert.Contains(loser.Reasons, r => r.Contains("Removed non-selected", StringComparison.Ordinal) && r.Contains("stream 2", StringComparison.Ordinal));
    }

    [Fact]
    public void A_kept_subtitle_with_no_diagnostic_note_gets_a_plain_fallback_reason()
    {
        var (probe, plan) = Plan();

        var kept = RulesPreview.BuildTrackRows(probe, plan).Single(r => r.Index == 3);

        Assert.True(kept.Kept);
        Assert.Equal("Subtitle language matches the configured selection.", Assert.Single(kept.Reasons));
    }

    [Fact]
    public void A_dropped_subtitle_with_no_diagnostic_note_gets_a_plain_fallback_reason()
    {
        var (probe, plan) = Plan();

        var dropped = RulesPreview.BuildTrackRows(probe, plan).Single(r => r.Index == 4);

        Assert.False(dropped.Kept);
        Assert.Equal("Removed — language not in the configured subtitle selection.", Assert.Single(dropped.Reasons));
    }

    [Fact]
    public void The_estimate_sums_only_the_dropped_streams_bitrate_times_duration()
    {
        var (probe, plan) = Plan();

        // Dropped: the jpn audio track (1,500,000 bit/s) and the spa subtitle (1,000 bit/s), over 120s.
        var estimate = RulesPreview.EstimateDroppedBytes(probe, plan, durationSeconds: 120.0);

        Assert.Equal((1_500_000L + 1_000L) / 8 * 120, estimate);
    }

    [Fact]
    public void With_no_known_duration_the_estimate_is_null_rather_than_a_misleading_zero()
    {
        var (probe, plan) = Plan();

        Assert.Null(RulesPreview.EstimateDroppedBytes(probe, plan, durationSeconds: null));
        Assert.Null(RulesPreview.EstimateDroppedBytes(probe, plan, durationSeconds: 0));
    }

    /// <summary>
    /// End to end for #495 (remove hearing-impaired subtitles), #496 (regional variants) and #497
    /// (per_language audio) together: the original Japanese track and an English dub are both shown
    /// kept, an English "(SDH)" subtitle is dropped outright, and of two French subtitles sharing the
    /// bare "fre" tag, only the one named "VFQ" survives a rule that names "fre-CA" specifically.
    /// </summary>
    private const string PerLanguageVariantSdhFixture = """
        {
          "format": {"duration": "120.0"},
          "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
            {"index": 1, "codec_type": "audio", "codec_name": "dts", "channels": 6, "bit_rate": "1500000",
             "tags": {"language": "jpn"}, "disposition": {"default": 1}},
            {"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000",
             "tags": {"language": "eng"}},
            {"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng", "title": "English (SDH)"}},
            {"index": 4, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "fre", "title": "VFQ"}},
            {"index": 5, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "fre", "title": "VFF"}}
          ]
        }
        """;

    private static (ProbeResult Probe, RemuxPlan Plan) PerLanguageVariantSdhPlan()
    {
        var probe = ProbeResult.Parse(PerLanguageVariantSdhFixture);
        var (video, audio, subtitles) = RemuxRules.SplitStreams(probe);
        var config = RemuxRules.DefaultConfig() with
        {
            PrimaryAudioLang = "jpn",
            SecondaryAudioLang = "eng",
            AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng", "fre-CA"],
            RemoveHearingImpairedSubs = true,
        };
        var plan = RemuxRules.PlanRemux(video, audio, subtitles, config);
        Assert.NotNull(plan);
        return (probe, plan!);
    }

    [Fact]
    public void Per_language_mode_keeps_the_original_and_the_dub_and_both_rows_say_so()
    {
        var (probe, plan) = PerLanguageVariantSdhPlan();

        var rows = RulesPreview.BuildTrackRows(probe, plan);

        var japanese = rows.Single(r => r.Index == 1);
        var english = rows.Single(r => r.Index == 2);
        Assert.True(japanese.Kept);
        Assert.True(english.Kept);
        Assert.True(japanese.Default);
        Assert.False(english.Default);
    }

    [Fact]
    public void A_hearing_impaired_named_subtitle_is_dropped_outright()
    {
        var (probe, plan) = PerLanguageVariantSdhPlan();

        var sdh = RulesPreview.BuildTrackRows(probe, plan).Single(r => r.Index == 3);

        Assert.False(sdh.Kept);
    }

    [Fact]
    public void A_rule_naming_a_specific_variant_keeps_only_that_variant()
    {
        var (probe, plan) = PerLanguageVariantSdhPlan();

        var rows = RulesPreview.BuildTrackRows(probe, plan);
        var quebecFrench = rows.Single(r => r.Index == 4);
        var franceFrench = rows.Single(r => r.Index == 5);

        Assert.True(quebecFrench.Kept);
        Assert.False(franceFrench.Kept);
    }
}
