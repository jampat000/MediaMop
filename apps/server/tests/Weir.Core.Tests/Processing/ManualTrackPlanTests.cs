using Weir.Core.Processing;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Processing;

/// <summary>
/// Unit tests for issue #501's manual track plan: classifying streams, validating an operator's choice against a
/// fresh probe, and building a <see cref="RemuxPlan"/> directly from that choice (skipping <see cref="RemuxRules.PlanRemux"/>).
/// </summary>
public sealed class ManualTrackPlanTests
{
    private static ProbeStreamInfo Stream(string json) => ProbeStreamInfo.Parse(json);

    private static readonly ProbeStreamInfo Video = Stream("""{"index": 0, "codec_type": "video", "codec_name": "h264"}""");
    private static readonly ProbeStreamInfo EnglishAudio = Stream("""{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng"}, "disposition": {"default": 1}}""");
    private static readonly ProbeStreamInfo CommentaryAudio = Stream("""{"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng", "title": "Director commentary"}}""");
    private static readonly ProbeStreamInfo EnglishSub = Stream("""{"index": 3, "codec_type": "subtitle", "tags": {"language": "eng"}}""");
    private static readonly ProbeStreamInfo FrenchSub = Stream("""{"index": 4, "codec_type": "subtitle", "tags": {"language": "fre"}}""");

    private static SplitProbeStreams Streams() => new([Video], [EnglishAudio, CommentaryAudio], [EnglishSub, FrenchSub]);

    [Fact]
    public void ClassifyIndices_reports_every_real_streams_kind()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());

        Assert.Equal(ManualTrackKind.Video, kinds[0]);
        Assert.Equal(ManualTrackKind.Audio, kinds[1]);
        Assert.Equal(ManualTrackKind.Audio, kinds[2]);
        Assert.Equal(ManualTrackKind.Subtitle, kinds[3]);
        Assert.Equal(ManualTrackKind.Subtitle, kinds[4]);
    }

    [Fact]
    public void A_choice_with_no_video_is_rejected()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());
        var choice = new ManualPlanChoice([new ManualKeepEntry(1, true, false)], [1]);

        Assert.False(ManualTrackPlan.TryValidate(choice, kinds, out var problem));
        Assert.Contains("video", problem, StringComparison.Ordinal);
    }

    [Fact]
    public void A_choice_with_no_audio_is_rejected()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());
        var choice = new ManualPlanChoice([new ManualKeepEntry(0, false, false)], [0]);

        Assert.False(ManualTrackPlan.TryValidate(choice, kinds, out var problem));
        Assert.Contains("audio", problem, StringComparison.Ordinal);
    }

    [Fact]
    public void A_choice_referencing_an_unknown_index_is_rejected()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());
        var choice = new ManualPlanChoice([new ManualKeepEntry(0, false, false), new ManualKeepEntry(99, true, false)], [0, 99]);

        Assert.False(ManualTrackPlan.TryValidate(choice, kinds, out var problem));
        Assert.Contains("99", problem, StringComparison.Ordinal);
    }

    [Fact]
    public void More_than_one_default_audio_track_is_rejected()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());
        var choice = new ManualPlanChoice(
            [new ManualKeepEntry(0, false, false), new ManualKeepEntry(1, true, false), new ManualKeepEntry(2, true, false)],
            [0, 1, 2]);

        Assert.False(ManualTrackPlan.TryValidate(choice, kinds, out var problem));
        Assert.Contains("one audio track", problem, StringComparison.Ordinal);
    }

    [Fact]
    public void More_than_one_default_subtitle_track_is_rejected()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());
        var choice = new ManualPlanChoice(
            [new ManualKeepEntry(0, false, false), new ManualKeepEntry(1, true, false), new ManualKeepEntry(3, true, true), new ManualKeepEntry(4, true, true)],
            [0, 1, 3, 4]);

        Assert.False(ManualTrackPlan.TryValidate(choice, kinds, out var problem));
        Assert.Contains("one subtitle track", problem, StringComparison.Ordinal);
    }

    [Fact]
    public void An_order_that_omits_a_kept_index_is_rejected()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());
        var choice = new ManualPlanChoice([new ManualKeepEntry(0, false, false), new ManualKeepEntry(1, true, false)], [0]);

        Assert.False(ManualTrackPlan.TryValidate(choice, kinds, out var problem));
        Assert.Contains("order", problem, StringComparison.Ordinal);
    }

    [Fact]
    public void A_well_formed_choice_validates()
    {
        var kinds = ManualTrackPlan.ClassifyIndices(Streams());
        var choice = new ManualPlanChoice([new ManualKeepEntry(0, false, false), new ManualKeepEntry(1, true, false), new ManualKeepEntry(3, false, true)], [0, 1, 3]);

        Assert.True(ManualTrackPlan.TryValidate(choice, kinds, out var problem));
        Assert.Equal(string.Empty, problem);
    }

    [Fact]
    public void BuildPlan_keeps_exactly_the_chosen_tracks_in_the_chosen_order_with_the_chosen_flags()
    {
        var streams = Streams();
        // Keep the commentary track instead of the plain English one, mark it default, and keep only the French subtitle as forced.
        var choice = new ManualPlanChoice(
            [new ManualKeepEntry(0, false, false), new ManualKeepEntry(2, true, false), new ManualKeepEntry(4, false, true)],
            [0, 2, 4]);

        var plan = ManualTrackPlan.BuildPlan(streams, choice);

        Assert.Equal([0], plan.VideoIndices);
        var audio = Assert.Single(plan.Audio);
        Assert.Equal(2, audio.InputIndex);
        Assert.True(audio.Default);
        Assert.Equal("eng", audio.LangLabel);
        var subtitle = Assert.Single(plan.Subtitles);
        Assert.Equal(4, subtitle.InputIndex);
        Assert.True(subtitle.Forced);
        Assert.False(subtitle.Default);
        Assert.Equal("fre", subtitle.LangLabel);
        Assert.Equal(0, plan.DefaultAudioOutputIndex);
        // Not selected — the plain English track was dropped in favor of the operator's choice.
        Assert.Contains(plan.RemovedAudio, line => line.Contains("stream 1", StringComparison.Ordinal));
        Assert.Contains("eng", plan.RemovedSubtitles);
    }

    [Fact]
    public void BuildPlan_orders_kept_tracks_by_the_order_list_not_their_probe_order()
    {
        var streams = Streams();
        var choice = new ManualPlanChoice(
            [new ManualKeepEntry(0, false, false), new ManualKeepEntry(3, false, false), new ManualKeepEntry(4, false, false), new ManualKeepEntry(1, true, false)],
            [0, 4, 3, 1]);

        var plan = ManualTrackPlan.BuildPlan(streams, choice);

        Assert.Equal([4, 3], plan.Subtitles.Select(t => t.InputIndex));
        Assert.Equal([1], plan.Audio.Select(t => t.InputIndex));
    }

    [Fact]
    public void BuildPlan_does_not_apply_automatic_mutations_the_operator_did_not_choose()
    {
        // The commentary track would normally be excluded by RemoveCommentary; a manual plan is authoritative.
        var streams = Streams();
        var choice = new ManualPlanChoice([new ManualKeepEntry(0, false, false), new ManualKeepEntry(2, true, false)], [0, 2]);

        var plan = ManualTrackPlan.BuildPlan(streams, choice);

        Assert.Equal(2, Assert.Single(plan.Audio).InputIndex);
        Assert.Empty(plan.RemovedImages);
        Assert.Empty(plan.RemovedAttachments);
        Assert.Empty(plan.MetadataNotes);
    }
}
