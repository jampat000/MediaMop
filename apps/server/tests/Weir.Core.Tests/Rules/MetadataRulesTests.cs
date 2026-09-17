using Weir.Core.Rules;

namespace Weir.Core.Tests.Rules;

/// <summary>
/// Ported from <c>apps/backend/tests/test_refiner_metadata_rules.py</c> and
/// <c>test_refiner_remux_rules_split_streams.py</c>. The two tests there that build the ffmpeg
/// argv (<c>build_ffmpeg_argv</c>) belong to the ffmpeg/ffprobe port and are not here.
/// </summary>
public sealed class MetadataRulesTests
{
    private const string Video0 = """{"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "24000/1001", "nb_frames": "150000"}""";

    private static string CoverArt(int index = 1, bool attachedPic = true) => attachedPic
        ? $$$"""{"index": {{{index}}}, "codec_type": "video", "codec_name": "mjpeg", "width": 600, "height": 900, "avg_frame_rate": "0/0", "nb_frames": "1", "disposition": {"attached_pic": 1, "default": 0}}"""
        : $$$"""{"index": {{{index}}}, "codec_type": "video", "codec_name": "mjpeg", "width": 600, "height": 900, "avg_frame_rate": "0/0", "nb_frames": "1"}""";

    private static readonly string[] EmptyLines = ["", "—", "-"];

    private static string Audio(int index = 2) =>
        $$$"""{"index": {{{index}}}, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "bit_rate": "640000", "tags": {"language": "eng"}, "disposition": {"default": 1}}""";

    private static string Attachment(int index = 3, string name = "Arial.ttf") =>
        $$$"""{"index": {{{index}}}, "codec_type": "attachment", "codec_name": "ttf", "tags": {"filename": "{{{name}}}"}}""";

    private static ProbeResult Probe(params string[] streams) => ProbeResult.Parse($$$"""{"streams": [{{{string.Join(", ", streams)}}}]}""");

    private static ProbeStreamInfo Stream(string json) => ProbeStreamInfo.Parse(json);

    private static RefinerRulesConfig Config(MetadataRules? metadata = null) =>
        metadata is null ? RemuxRules.DefaultConfig() : RemuxRules.DefaultConfig() with { Metadata = metadata };

    private static (RemuxPlan Plan, SplitProbeStreams Split) Plan(ProbeResult probe, RefinerRulesConfig config, bool withAttachments = false)
    {
        var split = RemuxRules.SplitStreams(probe);
        var plan = RemuxRules.PlanRemux(split.Video, split.Audio, split.Subtitles, config, withAttachments ? RemuxRules.AttachmentStreams(probe) : null);
        Assert.NotNull(plan);
        return (plan, split);
    }

    private static IEnumerable<long?> Indices(IEnumerable<ProbeStreamInfo> streams) => streams.Select(s => s.Index);

    // --- split_streams --------------------------------------------------------------------

    [Fact]
    public void Split_streams_orders_by_index()
    {
        var probe = ProbeResult.Parse("""{"streams": [{"index": 2, "codec_type": "audio"}, {"index": 0, "codec_type": "video"}, {"index": 1, "codec_type": "subtitle"}]}""");

        var split = RemuxRules.SplitStreams(probe);

        Assert.Equal([0L], Indices(split.Video));
        Assert.Equal([2L], Indices(split.Audio));
        Assert.Equal([1L], Indices(split.Subtitles));
    }

    // --- recognising a poster ------------------------------------------------------------

    [Fact]
    public void An_attached_pic_is_recognised_as_an_image() => Assert.True(MetadataStreams.IsImageStream(Stream(CoverArt())));

    [Fact]
    public void A_single_frame_mjpeg_with_no_disposition_is_still_recognised() =>
        Assert.True(MetadataStreams.IsImageStream(Stream(CoverArt(attachedPic: false))));

    [Fact]
    public void Real_video_is_not_mistaken_for_a_poster() => Assert.False(MetadataStreams.IsImageStream(Stream(Video0)));

    [Fact]
    public void Genuine_mjpeg_video_is_not_mistaken_for_a_poster()
    {
        var stream = Stream("""{"index": 0, "codec_type": "video", "codec_name": "mjpeg", "avg_frame_rate": "25/1", "nb_frames": "50000"}""");

        Assert.False(MetadataStreams.IsImageStream(stream));
    }

    [Fact]
    public void An_attachment_is_recognised()
    {
        Assert.True(MetadataStreams.IsAttachmentStream(Stream(Attachment())));
        Assert.False(MetadataStreams.IsAttachmentStream(Stream(Audio())));
    }

    [Fact]
    public void Video_and_images_are_always_separated_even_when_kept()
    {
        var (real, images) = MetadataStreams.SplitVideoAndImages([Stream(Video0), Stream(CoverArt(1))]);

        Assert.Equal([0L], Indices(real));
        Assert.Equal([1L], Indices(images));
    }

    [Fact]
    public void A_file_of_nothing_but_images_keeps_one_rather_than_planning_no_picture()
    {
        var (real, images) = MetadataStreams.SplitVideoAndImages([Stream(CoverArt(0)), Stream(CoverArt(1))]);

        Assert.Single(real);
        Assert.Single(images);
    }

    // --- the default changes nothing -----------------------------------------------------

    [Fact]
    public void By_default_a_poster_is_carried_through_exactly_as_before()
    {
        var (plan, _) = Plan(Probe(Video0, CoverArt(1), Audio(2)), Config());

        Assert.Equal([0, 1], plan.VideoIndices);
        Assert.Empty(plan.RemovedImages);
        Assert.Empty(plan.MetadataNotes);
    }

    [Fact]
    public void By_default_no_metadata_flags_reach_ffmpeg() => Assert.Empty(MetadataStreams.ArgvFlags(new MetadataRules()));

    [Fact]
    public void By_default_a_file_needing_nothing_else_is_not_remuxed()
    {
        var (plan, split) = Plan(Probe(Video0, CoverArt(1), Audio(2)), Config());

        Assert.False(RemuxRules.IsRemuxRequired(plan, split.Audio, split.Subtitles));
    }

    // --- removing --------------------------------------------------------------------

    [Fact]
    public void Removing_images_drops_the_poster_from_the_planned_streams()
    {
        var (plan, _) = Plan(Probe(Video0, CoverArt(1), Audio(2)), Config(new MetadataRules { RemoveImages = true }));

        Assert.Equal([0], plan.VideoIndices);
        var removed = Assert.Single(plan.RemovedImages);
        Assert.Contains("mjpeg", removed, StringComparison.Ordinal);
        Assert.Contains("600x900", removed, StringComparison.Ordinal);
    }

    [Fact]
    public void Removing_attachments_drops_an_attached_font()
    {
        var (plan, _) = Plan(Probe(Video0, Audio(1), Attachment(2, "Arial.ttf")), Config(new MetadataRules { RemoveAttachments = true }), withAttachments: true);

        var removed = Assert.Single(plan.RemovedAttachments);
        Assert.Contains("Arial.ttf", removed, StringComparison.Ordinal);
    }

    [Fact]
    public void Attachments_are_found_in_a_probe()
    {
        var probe = Probe(Video0, Audio(1), Attachment(2), Attachment(3, "Comic.ttf"));

        Assert.Equal([2L, 3L], Indices(RemuxRules.AttachmentStreams(probe)));
    }

    [Fact]
    public void Removing_the_title_leaves_other_metadata_alone()
    {
        var flags = MetadataStreams.ArgvFlags(new MetadataRules { RemoveTitle = true });

        Assert.Equal(["-metadata", "title="], flags);
        Assert.DoesNotContain("-map_metadata", flags);
    }

    [Fact]
    public void Removing_all_metadata_clears_everything_and_restates_the_title()
    {
        var flags = MetadataStreams.ArgvFlags(new MetadataRules { RemoveOtherMetadata = true, RemoveTitle = true });

        Assert.Equal(["-map_metadata", "-1"], flags.Take(2));
        Assert.Equal(["-metadata", "title="], flags.TakeLast(2));
    }

    [Fact]
    public void Removing_language_tags_is_its_own_flag() =>
        Assert.Equal(["-metadata:s", "language="], MetadataStreams.ArgvFlags(new MetadataRules { RemoveLanguageTags = true }));

    // --- the pass is required --------------------------------------------------------

    [Fact]
    public void A_file_whose_only_change_is_a_stripped_poster_is_remuxed()
    {
        var (plan, split) = Plan(Probe(Video0, CoverArt(1), Audio(2)), Config(new MetadataRules { RemoveImages = true }));

        Assert.True(RemuxRules.IsRemuxRequired(plan, split.Audio, split.Subtitles));
    }

    [Fact]
    public void A_file_whose_only_change_is_a_stripped_title_is_remuxed()
    {
        var (plan, split) = Plan(Probe(Video0, Audio(1)), Config(new MetadataRules { RemoveTitle = true }));

        Assert.True(RemuxRules.IsRemuxRequired(plan, split.Audio, split.Subtitles));
    }

    [Fact]
    public void A_file_whose_only_change_is_stripped_metadata_is_remuxed()
    {
        var (plan, split) = Plan(Probe(Video0, Audio(1)), Config(new MetadataRules { RemoveOtherMetadata = true }));

        Assert.True(RemuxRules.IsRemuxRequired(plan, split.Audio, split.Subtitles));
    }

    // --- what the operator is told ----------------------------------------------------

    [Fact]
    public void The_notes_say_what_was_removed()
    {
        var notes = MetadataStreams.RemovalNotes(new MetadataRules { RemoveImages = true, RemoveTitle = true }, [Stream(CoverArt())], []);

        Assert.Contains(notes, n => n.Contains("embedded image", StringComparison.Ordinal));
        Assert.Contains(notes, n => n.Contains("container title", StringComparison.Ordinal));
    }

    [Fact]
    public void The_display_line_is_empty_when_nothing_was_removed()
    {
        var (plan, _) = Plan(Probe(Video0, Audio(1)), Config());

        Assert.Contains(RemuxDisplay.MetadataRemovedLineFromPlan(plan), EmptyLines);
    }

    [Fact]
    public void The_display_line_names_a_removed_poster()
    {
        var (plan, _) = Plan(Probe(Video0, CoverArt(1), Audio(2)), Config(new MetadataRules { RemoveImages = true }));

        Assert.Contains("embedded image", RemuxDisplay.MetadataRemovedLineFromPlan(plan), StringComparison.Ordinal);
    }

}
