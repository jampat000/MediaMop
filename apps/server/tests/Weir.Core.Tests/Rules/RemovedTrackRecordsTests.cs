using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// <see cref="RemuxPlan.RemovedTrackRecords"/> (#509 step 1): the structured shadow of
/// <see cref="RemuxPlan.RemovedAudio"/>/<see cref="RemuxPlan.RemovedSubtitles"/>, built from the same
/// source data. These tests lock in the mapping for each way a track can be removed.
/// </summary>
public sealed class RemovedTrackRecordsTests
{
    private static ProbeStreamInfo Stream(string json) => ProbeStreamInfo.Parse(json);

    private static readonly ProbeStreamInfo Video = Stream("""{"index": 0, "codec_type": "video", "codec_name": "h264"}""");

    [Fact]
    public void A_commentary_excluded_track_is_recorded_with_its_language_and_codec()
    {
        var commentary = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "eng", "title": "Director commentary"}, "disposition": {"comment": 1}}""");
        var kept = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig() with { RemoveCommentary = true };

        var plan = RemuxRules.PlanRemux([Video], [commentary, kept], [], config);

        Assert.NotNull(plan);
        var record = Assert.Single(plan!.RemovedTrackRecords, r => r.Reason.Contains("commentary", StringComparison.Ordinal));
        Assert.Equal("eng", record.Language);
        Assert.Equal(RemovedTrackType.Audio, record.Type);
        Assert.Equal("aac", record.Codec);
        Assert.Null(record.Variant);
    }

    [Fact]
    public void A_non_selected_audio_candidate_is_recorded_with_its_own_language_and_codec()
    {
        var loser = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "jpn"}}""");
        var winner = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig() with { PrimaryAudioLang = "eng" };

        var plan = RemuxRules.PlanRemux([Video], [loser, winner], [], config);

        Assert.NotNull(plan);
        Assert.Equal(2, plan!.Audio[0].InputIndex);
        var record = Assert.Single(plan.RemovedTrackRecords);
        Assert.Equal("jpn", record.Language);
        Assert.Equal(RemovedTrackType.Audio, record.Type);
        Assert.Equal("aac", record.Codec);
        Assert.Contains("not selected", record.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Subtitle_mode_remove_all_records_every_subtitle_track()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var sub = Stream("""{"index": 2, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "spa"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeRemoveAll };

        var plan = RemuxRules.PlanRemux([Video], [audio], [sub], config);

        Assert.NotNull(plan);
        var record = Assert.Single(plan!.RemovedTrackRecords, r => r.Type == RemovedTrackType.Subtitle);
        Assert.Equal("spa", record.Language);
        Assert.Equal("subrip", record.Codec);
    }

    [Fact]
    public void A_subtitle_language_not_kept_is_recorded_distinctly_from_hearing_impaired_removal()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var frenchSub = Stream("""{"index": 2, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "fre"}}""");
        var hearingImpairedEnglishSub = Stream("""{"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}, "disposition": {"hearing_impaired": 1}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng"],
            RemoveHearingImpairedSubs = true,
        };

        var plan = RemuxRules.PlanRemux([Video], [audio], [frenchSub, hearingImpairedEnglishSub], config);

        Assert.NotNull(plan);
        Assert.Equal(2, plan!.RemovedTrackRecords.Count);
        var notKept = Assert.Single(plan.RemovedTrackRecords, r => r.Language == "fre");
        Assert.Contains("not kept", notKept.Reason, StringComparison.Ordinal);
        var hearingImpaired = Assert.Single(plan.RemovedTrackRecords, r => r.Language == "eng");
        Assert.Contains("hearing-impaired", hearingImpaired.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void An_unlabelled_track_is_recorded_as_und_with_an_unknown_codec()
    {
        var noLang = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000"}""");
        var kept = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");

        var plan = RemuxRules.PlanRemux([Video], [noLang, kept], [], RemuxRules.DefaultConfig());

        Assert.NotNull(plan);
        var record = Assert.Single(plan!.RemovedTrackRecords);
        Assert.Equal("und", record.Language);
    }
}
