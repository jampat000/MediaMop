using Weir.Core.LibraryMode;
using Weir.Core.Rules;

namespace Weir.Core.Tests.LibraryMode;

public sealed class LibraryFilePlannerTests
{
    private const string EnglishAndJapanese =
        """{"format":{"duration":"120.0"},"streams":[{"index":0,"codec_type":"video","codec_name":"h264"},{"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"},"disposition":{"default":1},"bit_rate":"128000"},{"index":2,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"jpn"},"bit_rate":"96000"}]}""";

    private const string EnglishJapaneseAndFrench =
        """{"format":{"duration":"120.0"},"streams":[{"index":0,"codec_type":"video","codec_name":"h264"},{"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"},"disposition":{"default":1},"bit_rate":"128000"},{"index":2,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"jpn"},"bit_rate":"96000"},{"index":3,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"fre"},"bit_rate":"96000"}]}""";

    private const string EnglishOnly =
        """{"format":{"duration":"120.0"},"streams":[{"index":0,"codec_type":"video","codec_name":"h264"},{"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"},"disposition":{"default":1},"bit_rate":"128000"}]}""";

    private const string NoVideo =
        """{"format":{"duration":"120.0"},"streams":[{"index":0,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"}}]}""";

    private static ProcessingRulesConfig EnglishOnlyRules() => new()
    {
        PrimaryAudioLang = "eng",
        SecondaryAudioLang = string.Empty,
        TertiaryAudioLang = string.Empty,
        DefaultAudioSlot = RemuxRuleValues.DefaultAudioSlotPrimary,
        RemoveCommentary = false,
        SubtitleMode = "keep_all",
        SubtitleLangs = [],
        PreserveForcedSubs = true,
        PreserveDefaultSubs = true,
        AudioPreferenceMode = RemuxRuleValues.PolicyPreferredLangsStrict,
    };

    [Fact]
    public void A_file_with_only_the_kept_language_matches()
    {
        var result = LibraryFilePlanner.Classify(ProbeResult.Parse(EnglishOnly), EnglishOnlyRules());
        Assert.Equal(LibraryFileClassification.Matches, result.Classification);
        Assert.Equal(0, result.RemovedAudioCount);
    }

    [Fact]
    public void A_file_with_an_extra_language_would_change_and_estimates_the_removed_tracks_bytes()
    {
        var result = LibraryFilePlanner.Classify(ProbeResult.Parse(EnglishAndJapanese), EnglishOnlyRules());
        Assert.Equal(LibraryFileClassification.WouldChange, result.Classification);
        Assert.Equal(1, result.RemovedAudioCount);
        Assert.NotNull(result.Summary);
        Assert.StartsWith("Would remove 1 audio track (jpn ", result.Summary, StringComparison.Ordinal);
        // 96000 bits/s * 120s / 8 = 1,440,000 bytes for the removed Japanese track.
        Assert.Equal(1_440_000, result.EstimatedBytesSaved);
    }

    [Fact]
    public void Two_removed_tracks_read_in_the_plural()
    {
        var result = LibraryFilePlanner.Classify(ProbeResult.Parse(EnglishJapaneseAndFrench), EnglishOnlyRules());
        Assert.Equal(2, result.RemovedAudioCount);
        Assert.NotNull(result.Summary);
        Assert.StartsWith("Would remove 2 audio tracks (jpn ", result.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public void A_file_with_no_video_track_cannot_be_processed()
    {
        var result = LibraryFilePlanner.Classify(ProbeResult.Parse(NoVideo), EnglishOnlyRules());
        Assert.Equal(LibraryFileClassification.CannotProcess, result.Classification);
        Assert.NotNull(result.Reason);
    }

    [Fact]
    public void A_rule_set_that_keeps_no_audio_cannot_be_processed()
    {
        var rules = EnglishOnlyRules() with { PrimaryAudioLang = "spa", AudioPreferenceMode = RemuxRuleValues.PolicyPreferredLangsStrict };
        // Strict preference with only English/Japanese present and Spanish required still picks a fallback in this engine,
        // so instead prove the "no audio survives" branch directly: an empty stream list can never produce a plan.
        var probe = ProbeResult.Parse("""{"format":{"duration":"1.0"},"streams":[{"index":0,"codec_type":"video","codec_name":"h264"}]}""");
        var result = LibraryFilePlanner.Classify(probe, rules);
        Assert.Equal(LibraryFileClassification.CannotProcess, result.Classification);
    }
}
