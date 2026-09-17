using System.Text.Json;
using Weir.Core.Media;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Media;

/// <summary>
/// Issue #500: <see cref="RemuxOutputValidation"/> checks a staged output against the whole plan — container
/// family, per-position track type, counts per type, disposition and language per kept track, new ffprobe
/// warnings and cleared metadata — instead of just an audio count and a duration floor.
/// </summary>
public sealed class RemuxOutputValidationTests
{
    private static RemuxPlan MakePlan(IReadOnlyList<int> videoIndices, IReadOnlyList<PlannedTrack> audio, IReadOnlyList<PlannedTrack> subtitles, MetadataRules? metadata = null) =>
        new() { VideoIndices = videoIndices, Audio = audio, Subtitles = subtitles, Metadata = metadata ?? new MetadataRules() };

    private static PlannedTrack Track(int index, string lang, bool @default = false, bool forced = false, TrackKind kind = TrackKind.Audio) =>
        new() { InputIndex = index, LangLabel = lang, Default = @default, Forced = forced, Kind = kind };

    private static PlannedTrack Subtitle(int index, string lang, bool @default = false, bool forced = false) => Track(index, lang, @default, forced, TrackKind.Subtitle);

    private static JsonElement Probe(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    // --- container family -------------------------------------------------------------------

    [Fact]
    public void A_container_flip_from_matroska_to_mp4_is_rejected()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");

        var error = Assert.Throws<MediaToolException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, "matroska,webm", 100.0, [], []));

        Assert.Contains("matroska/webm", error.Message, StringComparison.Ordinal);
        Assert.Contains("mov/mp4", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Webm_output_for_a_matroska_source_is_the_same_family_and_is_not_a_flip()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"format_name":"webm","duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");

        RemuxOutputValidation.ValidateAgainstPlan(output, plan, "matroska,webm", 100.0, [], []);
    }

    // --- track counts and positions ----------------------------------------------------------

    [Fact]
    public void A_missing_subtitle_track_is_reported_with_the_exact_counts()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], [Subtitle(2, "eng"), Subtitle(3, "fre"), Subtitle(4, "spa")]);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}},{"codec_type":"subtitle","tags":{"language":"eng"}},{"codec_type":"subtitle","tags":{"language":"fre"}}]}""");

        var error = Assert.Throws<MediaToolException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []));

        Assert.Equal("Planned 3 subtitle track(s), output has 2.", error.Message);
    }

    [Fact]
    public void Reordered_subtitle_tracks_are_caught_even_though_the_type_and_count_match()
    {
        // Same counts, same codec_type at every position (both are "subtitle") — only the language tag at each
        // position reveals the swap, which is exactly why #500 checks language per position, not just counts.
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], [Subtitle(2, "eng"), Subtitle(3, "fre")]);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}},{"codec_type":"subtitle","tags":{"language":"fre"}},{"codec_type":"subtitle","tags":{"language":"eng"}}]}""");

        var error = Assert.Throws<MediaToolException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []));

        Assert.Contains("position 2", error.Message, StringComparison.Ordinal);
        Assert.Contains("'eng'", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_dropped_subtitle_track_that_the_plan_never_kept_does_not_fail_a_correct_output()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");

        RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []);
    }

    [Fact]
    public void A_lost_default_flag_on_the_kept_audio_track_is_caught()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":0},"tags":{"language":"eng"}}]}""");

        var error = Assert.Throws<MediaToolException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []));

        Assert.Contains("default=True", error.Message, StringComparison.Ordinal);
        Assert.Contains("default=False", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_forced_subtitle_that_lost_its_flag_is_caught()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], [Subtitle(2, "eng", forced: true)]);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}},{"codec_type":"subtitle","disposition":{"forced":0},"tags":{"language":"eng"}}]}""");

        var error = Assert.Throws<MediaToolException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []));

        Assert.Contains("forced=True", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Language_tag_variants_that_normalize_the_same_are_not_a_mismatch()
    {
        // The plan's language is already normalized ("eng"); a raw output tag like "eng-US" or "ENG" must be
        // normalized the same way before comparing, or a byte-for-byte-correct output would fail for no reason.
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng-US"}}]}""");

        RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []);
    }

    [Fact]
    public void A_language_tag_stripped_by_the_metadata_rule_is_not_checked()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], [], metadata: new MetadataRules { RemoveLanguageTags = true });
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1}}]}""");

        RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []);
    }

    // --- duration ------------------------------------------------------------------------------

    [Fact]
    public void A_short_clip_missing_a_few_seconds_is_caught_by_the_tightened_tolerance_floor()
    {
        // At 60s, 1% is 0.6s. The reference's old max(5s, 1%) tolerance would have let 3 seconds go missing from a
        // short clip unnoticed (3 < 5); #500's max(0.5s, 1%) does not (3 > 0.6).
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"duration":"57.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");

        var error = Assert.Throws<MediaCompletenessException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 60.0, [], []));

        Assert.Contains("57.0s of 60.0s expected", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Expected_duration_ignores_a_dropped_stream_that_ran_longer_than_every_kept_stream()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var source = Probe(
            """{"streams":[{"index":0,"codec_type":"video","duration":"1200.0"},{"index":1,"codec_type":"audio","duration":"1200.0"},{"index":2,"codec_type":"subtitle","duration":"1500.0"}]}""");

        Assert.Equal(1200.0, RemuxOutputValidation.ExpectedDurationFromKeptStreams(source, plan));
    }

    [Fact]
    public void A_correct_output_is_not_penalized_for_a_dropped_subtitle_that_ran_longer_than_the_feature()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"duration":"1199.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");

        // Expected (1200.0) comes from the kept streams only (see the test above), not the longer subtitle track
        // the plan drops, so a correct 1199s output is well within tolerance instead of failing as "incomplete".
        RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 1200.0, [], []);
    }

    [Fact]
    public void A_matroska_duration_tag_is_read_when_the_stream_reports_no_duration_of_its_own()
    {
        Assert.Equal(1230.5, RemuxOutputValidation.ParseTagsDuration("00:20:30.500000000"));
        Assert.Null(RemuxOutputValidation.ParseTagsDuration("not-a-duration"));
        Assert.Null(RemuxOutputValidation.ParseTagsDuration(null));
    }

    // --- warnings ------------------------------------------------------------------------------

    [Fact]
    public void A_new_ffprobe_warning_on_the_output_fails_validation()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");
        string[] sourceWarnings = ["[matroska @ 0x1122] Known warning"];
        string[] outputWarnings = ["[matroska @ 0x1122] Known warning", "[matroska @ 0x3344] A brand new warning"];

        var error = Assert.Throws<MediaToolException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, sourceWarnings, outputWarnings));

        Assert.Contains("A brand new warning", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_warning_that_only_differs_by_address_or_offset_is_not_a_new_warning()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], []);
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");
        string[] sourceWarnings = ["[matroska @ 0x1122] Non-monotonic DTS, previous: 100, current: 90"];
        string[] outputWarnings = ["[matroska @ 0x99aa] Non-monotonic DTS, previous: 555, current: 200"];

        RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, sourceWarnings, outputWarnings);
    }

    // --- metadata ------------------------------------------------------------------------------

    [Fact]
    public void A_cleared_title_that_still_appears_on_the_output_is_caught()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], [], metadata: new MetadataRules { RemoveTitle = true });
        var output = Probe(
            """{"format":{"duration":"100.0","tags":{"title":"Still Here"}},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");

        var error = Assert.Throws<MediaToolException>(() => RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []));

        Assert.Contains("container title", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_cleared_title_that_is_actually_gone_passes()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], [], metadata: new MetadataRules { RemoveTitle = true });
        var output = Probe(
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video"},{"codec_type":"audio","disposition":{"default":1},"tags":{"language":"eng"}}]}""");

        RemuxOutputValidation.ValidateAgainstPlan(output, plan, null, 100.0, [], []);
    }
}
