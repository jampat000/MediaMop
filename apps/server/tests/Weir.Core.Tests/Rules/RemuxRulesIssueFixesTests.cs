using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Focused tests for the defects fixed by issue #537 (items 1, 2, 3, 5, 6 — item 4 is covered
/// separately below) and the engine-side plumbing added for item 4. The golden corpus already
/// proves these against the full 106-case suite via <c>golden/overrides</c>; these tests isolate
/// one behaviour each so a regression points straight at the cause.
/// </summary>
public sealed class RemuxRulesIssueFixesTests
{
    private static ProbeStreamInfo Stream(string json) => ProbeStreamInfo.Parse(json);

    private static readonly ProbeStreamInfo Video = Stream("""{"index": 0, "codec_type": "video", "codec_name": "h264"}""");

    // --- item 2: a "title" sorter compares the stream's own title, not the codec name ------

    [Fact]
    public void A_title_sorter_compares_the_stream_title_not_the_codec_name()
    {
        // Stream 1's codec is literally "ac3", but it has no title tag. Stream 2's codec is
        // "truehd", but its title tag happens to mention "ac3". Before the fix, the sorter was
        // handed the codec name, so stream 1 (codec "ac3") would win; after the fix, only a real
        // title match wins, so stream 2 (title contains "ac3") wins instead.
        var untitledAc3 = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var titledTrueHd = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "truehd", "channels": 8, "bit_rate": "4000000", "tags": {"language": "eng", "title": "Commentary track (ac3 downmix available)"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            RemoveCommentary = false,
            AudioSortersJson = """[{"field": "title", "value": "ac3"}]""",
        };

        var plan = RemuxRules.PlanRemux([Video], [untitledAc3, titledTrueHd], [], config);

        Assert.NotNull(plan);
        Assert.Equal(2, plan!.Audio[0].InputIndex);
    }

    // --- item 3: configured subtitle languages are normalized like a track's own tag ------

    [Fact]
    public void Configured_subtitle_languages_are_normalized_like_a_tracks_own_language_tag()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var englishSub = Stream("""{"index": 2, "codec_type": "subtitle", "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            // An operator would naturally type the language the way the file's own tag reads
            // ("ENG"), or the way a picker offers it ("en-US"); both must match a plain "eng" tag.
            SubtitleLangs = ["ENG"],
        };

        var plan = RemuxRules.PlanRemux([Video], [audio], [englishSub], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Subtitles);
        Assert.Equal(2, plan.Subtitles[0].InputIndex);
        Assert.Empty(plan.RemovedSubtitles);
    }

    // --- item 5: a non-string tag value is missing, not stringified -----------------------

    [Fact]
    public void A_list_valued_title_no_longer_falsely_marks_a_track_as_commentary()
    {
        // str(["Commentary"]) is "['Commentary']", which contains "commentary" — the exact
        // false match the issue describes. The value is not a string, so it must be ignored.
        var listTitled = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": null, "title": ["Commentary"]}}""");
        var config = RemuxRules.DefaultConfig() with { RemoveCommentary = true };

        var plan = RemuxRules.PlanRemux([Video], [listTitled], [], config);

        Assert.NotNull(plan);
        Assert.Empty(plan!.RemovedAudio);
        Assert.Equal(1, plan.Audio[0].InputIndex);
        Assert.False(plan.Audio[0].Commentary);
    }

    [Fact]
    public void A_null_language_tag_is_missing_not_the_text_none()
    {
        var nullLanguage = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": null}}""");

        var plan = RemuxRules.PlanRemux([Video], [nullLanguage], [], RemuxRules.DefaultConfig());

        Assert.NotNull(plan);
        // str(None) == "None"; a real, if bogus, three-letter-looking value must not appear here.
        Assert.Equal(string.Empty, plan!.Audio[0].LangLabel);
    }

    // --- item 6: one bad ffprobe value must not fail the whole plan ------------------------

    [Fact]
    public void An_unparseable_bit_rate_is_treated_as_unknown_not_a_failure()
    {
        // ffprobe really does emit "N/A" for an unknown bit rate.
        var unknownBitRate = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6, "bit_rate": "N/A", "tags": {"language": "eng"}}""");

        var plan = RemuxRules.PlanRemux([Video], [unknownBitRate], [], RemuxRules.DefaultConfig());

        Assert.NotNull(plan);
        Assert.Equal(0, plan!.Audio[0].Bitrate);
    }

    [Fact]
    public void An_audio_stream_with_no_usable_index_is_skipped_not_a_failure()
    {
        var good = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var noIndex = Stream("""{"codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}}""");

        var plan = RemuxRules.PlanRemux([Video], [good, noIndex], [], RemuxRules.DefaultConfig());

        Assert.NotNull(plan);
        Assert.Equal(1, plan!.Audio[0].InputIndex);
        Assert.Empty(plan.RemovedAudio);
    }

    [Fact]
    public void A_subtitle_stream_with_no_usable_index_is_skipped_not_a_failure()
    {
        var audio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}}""");
        var noIndex = Stream("""{"codec_type": "subtitle", "tags": {"language": "fre"}}""");
        var config = RemuxRules.DefaultConfig() with { SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected, SubtitleLangs = ["fre"] };

        var plan = RemuxRules.PlanRemux([Video], [audio], [noIndex], config);

        Assert.NotNull(plan);
        Assert.Empty(plan!.Subtitles);
        Assert.Empty(plan.RemovedSubtitles);
    }

    // --- item 4: the engine accepts a preferred-language decision cleanly ------------------

    [Fact]
    public void WithOriginalLanguage_copies_the_outcome_into_the_config_in_one_call()
    {
        var config = RemuxRules.DefaultConfig();
        var outcome = new OriginalLanguageOutcome { PreferredIndices = [3, 1], Note = "Kept audio in the original language (fre)." };

        var updated = config.WithOriginalLanguage(outcome);

        Assert.Equal([3, 1], updated.PreferredAudioIndices);
        Assert.Equal("Kept audio in the original language (fre).", updated.OriginalLanguageNote);
        // The base config is untouched — this is a pure, ordinary `with` copy.
        Assert.Empty(config.PreferredAudioIndices);
        Assert.Equal(string.Empty, config.OriginalLanguageNote);
    }
}
