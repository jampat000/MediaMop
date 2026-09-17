using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Issue #497: keep more than one audio track (one per configured language slot), cap subtitles
/// per language by quality, and put content tier (main &gt; dub/audio description &gt; commentary)
/// first in the default audio sorters. The golden corpus (<see cref="GoldenParityTests"/>) already
/// proves <c>audio_keep_mode: single</c> gives identical plans to today (585 pre-existing cases,
/// 80 of them carrying a wording-only override for the new default sorter); these tests isolate
/// the new behaviour so a regression points straight at the cause.
/// </summary>
public sealed class Issue497Tests
{
    private static ProbeStreamInfo Stream(string json) => ProbeStreamInfo.Parse(json);

    private static readonly ProbeStreamInfo Video = Stream("""{"index": 0, "codec_type": "video", "codec_name": "h264"}""");

    // --- audio_keep_mode: single is the default and never changes today's plans -----------

    [Fact]
    public void Single_is_the_default_audio_keep_mode()
    {
        Assert.Equal(RemuxRuleValues.AudioKeepModeSingle, RemuxRules.DefaultConfig().AudioKeepMode);
    }

    // --- audio_keep_mode: per_language ------------------------------------------------------

    [Fact]
    public void Per_language_keeps_the_original_and_a_dub_with_the_original_as_default()
    {
        var japanese = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "flac", "channels": 2, "bit_rate": "1000000", "tags": {"language": "jpn"}}""");
        var englishDub = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 6, "bit_rate": "384000", "tags": {"language": "eng", "title": "English Dub"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
            PrimaryAudioLang = "jpn",
            SecondaryAudioLang = "eng",
        };

        var plan = RemuxRules.PlanRemux([Video], [japanese, englishDub], [], config);

        Assert.NotNull(plan);
        Assert.Equal(2, plan!.Audio.Count);
        Assert.Empty(plan.RemovedAudio);
        var jpnTrack = Assert.Single(plan.Audio, t => t.InputIndex == 1);
        var engTrack = Assert.Single(plan.Audio, t => t.InputIndex == 2);
        Assert.True(jpnTrack.Default, "the primary (Japanese) slot is the default when default_audio_slot is unset");
        Assert.False(engTrack.Default);
        Assert.Equal(plan.Audio.ToList().IndexOf(jpnTrack), plan.DefaultAudioOutputIndex);
    }

    [Fact]
    public void Per_language_skips_a_configured_slot_with_no_matching_track()
    {
        var english = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "eng"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
            PrimaryAudioLang = "eng",
            SecondaryAudioLang = "jpn",
            TertiaryAudioLang = "fre",
        };

        var plan = RemuxRules.PlanRemux([Video], [english], [], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Audio);
        Assert.Equal(1, plan.Audio[0].InputIndex);
        Assert.True(plan.Audio[0].Default);
    }

    [Fact]
    public void Per_language_never_keeps_zero_audio_even_when_no_slot_matches()
    {
        var spanish = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6, "bit_rate": "448000", "tags": {"language": "spa"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
            PrimaryAudioLang = "eng",
            SecondaryAudioLang = "jpn",
            TertiaryAudioLang = "",
        };

        var plan = RemuxRules.PlanRemux([Video], [spanish], [], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Audio);
        Assert.Equal(1, plan.Audio[0].InputIndex);
        Assert.True(plan.Audio[0].Default);
    }

    [Fact]
    public void Per_language_still_fails_only_when_there_is_no_candidate_at_all()
    {
        var commentary = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6, "tags": {"language": "eng", "title": "Director's Commentary"}}""");
        var config = RemuxRules.DefaultConfig() with { AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage, RemoveCommentary = true };

        var plan = RemuxRules.PlanRemux([Video], [commentary], [], config);

        Assert.Null(plan);
    }

    [Fact]
    public void Per_language_is_variant_aware_and_keeps_both_french_variants()
    {
        // "VFQ" self-identifies Quebec French; "VFF" self-identifies France French (LanguageVariants).
        var quebecFrench = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6, "bit_rate": "448000", "tags": {"language": "fre", "title": "VFQ"}}""");
        var franceFrench = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "fre", "title": "VFF"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
            PrimaryAudioLang = "fre-CA",
            SecondaryAudioLang = "fre-FR",
        };

        var plan = RemuxRules.PlanRemux([Video], [quebecFrench, franceFrench], [], config);

        Assert.NotNull(plan);
        Assert.Equal(2, plan!.Audio.Count);
        var quebec = Assert.Single(plan.Audio, t => t.InputIndex == 1);
        var france = Assert.Single(plan.Audio, t => t.InputIndex == 2);
        Assert.Equal("fre-CA", quebec.Variant);
        Assert.Equal("fre-FR", france.Variant);
        Assert.True(quebec.Default, "the primary slot (fre-CA) is the default");
    }

    [Fact]
    public void A_plain_base_language_slot_still_matches_any_variant_under_per_language()
    {
        // Issue #496 rule reused here: a plain base slot ("fre") matches every variant of it.
        var quebecFrench = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6, "tags": {"language": "fre", "title": "VFQ"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            AudioKeepMode = RemuxRuleValues.AudioKeepModePerLanguage,
            PrimaryAudioLang = "fre",
            SecondaryAudioLang = "jpn",
        };

        var plan = RemuxRules.PlanRemux([Video], [quebecFrench], [], config);

        Assert.NotNull(plan);
        Assert.Single(plan!.Audio);
        Assert.Equal(1, plan.Audio[0].InputIndex);
    }

    // --- default audio sorters: content tier (main > dub/audio description > commentary) --

    [Fact]
    public void A_commentary_track_with_more_channels_never_beats_the_main_track()
    {
        var main = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 2, "bit_rate": "192000", "tags": {"language": "eng"}}""");
        var commentary = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "truehd", "channels": 8, "bit_rate": "4000000", "tags": {"language": "eng", "title": "Director's Commentary"}}""");
        var config = RemuxRules.DefaultConfig() with { RemoveCommentary = false };

        var plan = RemuxRules.PlanRemux([Video], [main, commentary], [], config);

        Assert.NotNull(plan);
        Assert.Equal(1, plan!.Audio[0].InputIndex);
    }

    [Fact]
    public void A_dub_track_with_more_channels_never_beats_the_main_track()
    {
        var main = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 2, "bit_rate": "192000", "tags": {"language": "eng"}}""");
        var dub = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "truehd", "channels": 8, "bit_rate": "4000000", "tags": {"language": "eng", "title": "German Dubbed"}}""");

        var plan = RemuxRules.PlanRemux([Video], [main, dub], [], RemuxRules.DefaultConfig());

        Assert.NotNull(plan);
        Assert.Equal(1, plan!.Audio[0].InputIndex);
    }

    // --- subtitle_max_per_language and subtitle_quality_strategy ---------------------------

    private static readonly ProbeStreamInfo SomeAudio =
        Stream("""{"index": 10, "codec_type": "audio", "codec_name": "aac", "channels": 2, "bit_rate": "128000", "tags": {"language": "eng"}}""");

    private static ProbeStreamInfo EnglishSub(int index, string codec, string title = "") =>
        Stream(
            "{\"index\": " + index +
            ", \"codec_type\": \"subtitle\", \"codec_name\": " + System.Text.Json.JsonSerializer.Serialize(codec) +
            ", \"tags\": {\"language\": \"eng\", \"title\": " + System.Text.Json.JsonSerializer.Serialize(title) + "}}");

    [Fact]
    public void Zero_max_per_language_is_unlimited_and_keeps_every_track_unchanged()
    {
        var subs = new[] { EnglishSub(1, "subrip"), EnglishSub(2, "ass"), EnglishSub(3, "hdmv_pgs_subtitle") };
        var config = RemuxRules.DefaultConfig() with
        {
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng"],
            SubtitleMaxPerLanguage = 0,
        };

        var plan = RemuxRules.PlanRemux([Video], [SomeAudio], subs, config);

        Assert.NotNull(plan);
        Assert.Equal(3, plan!.Subtitles.Count);
    }

    [Theory]
    [InlineData(RemuxRuleValues.SubtitleStrategyTextFirst, 2)]
    [InlineData(RemuxRuleValues.SubtitleStrategyImageFirst, 4)]
    [InlineData(RemuxRuleValues.SubtitleStrategyAccessibility, 3)]
    public void Three_english_tracks_become_one_under_each_strategy_with_forced_exempt(string strategy, int expectedKeptIndex)
    {
        // stream 1: forced (always kept, never counts toward the cap)
        // stream 2: regular, text (SRT)
        // stream 3: SDH, text (SRT)
        // stream 4: regular, image (PGS)
        var forced = Stream("""{"index": 1, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng", "title": "Forced"}}""");
        var regularText = EnglishSub(2, "subrip");
        var sdhText = Stream("""{"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng", "title": "English (SDH)"}}""");
        var regularImage = EnglishSub(4, "hdmv_pgs_subtitle");
        var config = RemuxRules.DefaultConfig() with
        {
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng"],
            SubtitleMaxPerLanguage = 1,
            SubtitleQualityStrategy = strategy,
        };

        var plan = RemuxRules.PlanRemux([Video], [SomeAudio], [forced, regularText, sdhText, regularImage], config);

        Assert.NotNull(plan!);
        var indices = plan.Subtitles.Select(t => t.InputIndex).OrderBy(i => i).ToList();
        Assert.Equal([1, expectedKeptIndex], indices);
        Assert.Contains(plan.AudioSelectionNotes, n => n.Contains("kept the", StringComparison.Ordinal) && n.Contains(" track over ", StringComparison.Ordinal));
    }

    [Fact]
    public void A_forced_track_kept_under_preserve_forced_never_counts_toward_the_cap()
    {
        var forcedOne = Stream("""{"index": 1, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng", "title": "Forced"}}""");
        var forcedTwo = Stream("""{"index": 2, "codec_type": "subtitle", "codec_name": "subrip", "disposition": {"forced": 1}, "tags": {"language": "eng"}}""");
        var regular = EnglishSub(3, "subrip");
        var config = RemuxRules.DefaultConfig() with
        {
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng"],
            SubtitleMaxPerLanguage = 1,
            PreserveForcedSubs = true,
        };

        var plan = RemuxRules.PlanRemux([Video], [SomeAudio], [forcedOne, forcedTwo, regular], config);

        Assert.NotNull(plan);
        // Both forced tracks are exempt; only the single regular track is subject to the cap
        // (and there is only one, so nothing is dropped).
        var indices = plan!.Subtitles.Select(t => t.InputIndex).OrderBy(i => i).ToList();
        Assert.Equal([1, 2, 3], indices);
    }

    [Fact]
    public void The_cap_applies_per_language_independently()
    {
        var englishOne = EnglishSub(1, "subrip");
        var englishTwo = EnglishSub(2, "hdmv_pgs_subtitle");
        var french = Stream("""{"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "fre"}}""");
        var config = RemuxRules.DefaultConfig() with
        {
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng", "fre"],
            SubtitleMaxPerLanguage = 1,
        };

        var plan = RemuxRules.PlanRemux([Video], [SomeAudio], [englishOne, englishTwo, french], config);

        Assert.NotNull(plan);
        var indices = plan!.Subtitles.Select(t => t.InputIndex).OrderBy(i => i).ToList();
        // The English cap drops the PGS track (text_first is the default); French is untouched
        // because there is only one French candidate.
        Assert.Equal([1, 3], indices);
    }
}
