using System.Text.Json;
using Weir.Core.Media;
using Weir.Core.Rules;

namespace Weir.Core.Tests.Media;

/// <summary>
/// Issue #548: the mkvmerge argv for a <see cref="RemuxPlan"/>, and the track-id mapping it depends on.
/// <para>
/// The mapping is the part worth proving hardest. mkvmerge numbers its own tracks and a plan is built from
/// ffprobe indices; the two diverge wherever Matroska stores something as an attachment that ffprobe reports
/// as a stream — cover art above all. The fixtures here are the shapes measured on real files (see
/// <see cref="MkvmergeCommands"/>'s remarks) rather than invented ones.
/// </para>
/// </summary>
public sealed class MkvmergeCommandsTests
{
    private static RemuxPlan MakePlan(
        IReadOnlyList<int> videoIndices,
        IReadOnlyList<PlannedTrack> audio,
        IReadOnlyList<PlannedTrack> subtitles,
        MetadataRules? metadata = null) =>
        new() { VideoIndices = videoIndices, Audio = audio, Subtitles = subtitles, Metadata = metadata ?? new MetadataRules() };

    private static PlannedTrack Track(int index, string lang, bool @default = false, bool forced = false, TrackKind kind = TrackKind.Audio) =>
        new() { InputIndex = index, LangLabel = lang, Default = @default, Forced = forced, Kind = kind };

    private static PlannedTrack Subtitle(int index, string lang, bool @default = false, bool forced = false) =>
        Track(index, lang, @default, forced, TrackKind.Subtitle);

    private static IReadOnlyList<ProbeStreamInfo> Streams(string json)
    {
        using var document = JsonDocument.Parse(json);
        return [.. document.RootElement.EnumerateArray().Select(element => new ProbeStreamInfo(element.Clone()))];
    }

    private static MkvmergeIdentification Identify(string json)
    {
        using var document = JsonDocument.Parse(json);
        return MkvmergeCommands.ParseIdentification(document.RootElement);
    }

    /// <summary>
    /// The real file this was measured on: video, one E-AC-3 track, two SubRip tracks and a <c>cover</c>
    /// attachment, which ffprobe reports as a sixth stream flagged <c>attached_pic</c>.
    /// </summary>
    private const string StreamsWithCoverArt = """
        [{"index":0,"codec_type":"video","disposition":{"attached_pic":0}},
         {"index":1,"codec_type":"audio","disposition":{"attached_pic":0}},
         {"index":2,"codec_type":"subtitle","disposition":{"attached_pic":0}},
         {"index":3,"codec_type":"subtitle","disposition":{"attached_pic":0}},
         {"index":4,"codec_type":"video","codec_name":"mjpeg","disposition":{"attached_pic":1}}]
        """;

    private const string IdentificationWithCoverArt = """
        {"tracks":[{"id":0,"type":"video"},{"id":1,"type":"audio"},{"id":2,"type":"subtitles"},{"id":3,"type":"subtitles"}],
         "attachments":[{"id":1,"file_name":"cover.jpg","content_type":"image/jpeg"}],
         "chapters":[{"num_entries":3}]}
        """;

    // --- identification ---------------------------------------------------------------------

    [Fact]
    public void Identification_reads_tracks_attachments_and_chapters()
    {
        var identification = Identify(IdentificationWithCoverArt);

        Assert.Equal([0, 1, 2, 3], identification.Tracks.Select(track => track.Id));
        Assert.Equal(["video", "audio", "subtitles", "subtitles"], identification.Tracks.Select(track => track.Type));
        Assert.Equal(3, identification.ChapterEntries);
        var attachment = Assert.Single(identification.Attachments);
        Assert.Equal(1, attachment.Id);
        Assert.True(attachment.IsCoverArt);
    }

    [Theory]
    [InlineData("cover.jpg", "image/jpeg", true)]
    [InlineData("small_cover.png", "image/png", true)]
    // The Matroska cover-art convention is a reserved *name*, so a mistyped MIME type is still cover art.
    [InlineData("cover.jpg", "application/octet-stream", true)]
    [InlineData("TestFont.ttf", "font/ttf", false)]
    [InlineData("subtitles.ass", "text/x-ssa", false)]
    public void Cover_art_is_told_apart_from_other_attachments(string fileName, string contentType, bool expected) =>
        Assert.Equal(expected, new MkvmergeAttachment(1, contentType, fileName).IsCoverArt);

    // --- track id mapping -------------------------------------------------------------------

    [Fact]
    public void Cover_art_is_not_a_track_so_the_indices_still_line_up()
    {
        var map = MkvmergeCommands.MapStreamIndicesToTrackIds(Streams(StreamsWithCoverArt), Identify(IdentificationWithCoverArt));

        // The cover (ffprobe stream 4) takes no part; every other stream maps to the track of the same ordinal.
        Assert.Equal(new Dictionary<int, int> { [0] = 0, [1] = 1, [2] = 2, [3] = 3 }, map);
    }

    [Fact]
    public void Cover_art_before_the_other_tracks_shifts_every_id()
    {
        // The case that makes "index == id" wrong rather than merely unproven.
        var streams = Streams("""
            [{"index":0,"codec_type":"video","codec_name":"mjpeg","disposition":{"attached_pic":1}},
             {"index":1,"codec_type":"video","disposition":{"attached_pic":0}},
             {"index":2,"codec_type":"audio","disposition":{"attached_pic":0}}]
            """);
        var identification = Identify("""{"tracks":[{"id":0,"type":"video"},{"id":1,"type":"audio"}],"attachments":[{"id":1,"file_name":"cover.jpg","content_type":"image/jpeg"}]}""");

        var map = MkvmergeCommands.MapStreamIndicesToTrackIds(streams, identification);

        Assert.Equal(new Dictionary<int, int> { [1] = 0, [2] = 1 }, map);
    }

    [Fact]
    public void An_ffprobe_attachment_stream_is_not_a_track_either()
    {
        var streams = Streams("""
            [{"index":0,"codec_type":"video","disposition":{"attached_pic":0}},
             {"index":1,"codec_type":"audio","disposition":{"attached_pic":0}},
             {"index":2,"codec_type":"attachment","codec_name":"ttf"}]
            """);
        var identification = Identify("""{"tracks":[{"id":0,"type":"video"},{"id":1,"type":"audio"}],"attachments":[{"id":1,"file_name":"TestFont.ttf","content_type":"font/ttf"}]}""");

        Assert.Equal(new Dictionary<int, int> { [0] = 0, [1] = 1 }, MkvmergeCommands.MapStreamIndicesToTrackIds(streams, identification));
    }

    [Fact]
    public void A_count_that_does_not_match_is_refused_rather_than_guessed()
    {
        var streams = Streams("""[{"index":0,"codec_type":"video"},{"index":1,"codec_type":"audio"}]""");
        var identification = Identify("""{"tracks":[{"id":0,"type":"video"}]}""");

        var error = Assert.Throws<MkvmergeTrackMappingException>(
            () => MkvmergeCommands.MapStreamIndicesToTrackIds(streams, identification));

        Assert.Equal(
            "mkvmerge reported 1 track but ffprobe reported 2 matching streams, so a plan built from ffprobe indices "
            + "cannot be addressed to mkvmerge safely.",
            error.Message);
    }

    [Fact]
    public void A_count_mismatch_the_other_way_reads_in_english_too()
    {
        var streams = Streams("""[{"index":0,"codec_type":"video"}]""");
        var identification = Identify("""{"tracks":[{"id":0,"type":"video"},{"id":1,"type":"audio"}]}""");

        var error = Assert.Throws<MkvmergeTrackMappingException>(
            () => MkvmergeCommands.MapStreamIndicesToTrackIds(streams, identification));

        Assert.StartsWith("mkvmerge reported 2 tracks but ffprobe reported 1 matching stream, so", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_type_that_does_not_match_is_refused_rather_than_guessed()
    {
        var streams = Streams("""[{"index":0,"codec_type":"video"},{"index":1,"codec_type":"audio"}]""");
        var identification = Identify("""{"tracks":[{"id":0,"type":"video"},{"id":1,"type":"subtitles"}]}""");

        var error = Assert.Throws<MkvmergeTrackMappingException>(
            () => MkvmergeCommands.MapStreamIndicesToTrackIds(streams, identification));

        Assert.Contains("do not line up", error.Message, StringComparison.Ordinal);
    }

    // --- argv -------------------------------------------------------------------------------

    private static IReadOnlyList<string> Argv(RemuxPlan plan, string? identification = null, string destination = "out.mkv")
    {
        var parsed = Identify(identification ?? IdentificationWithCoverArt);
        var map = MkvmergeCommands.MapStreamIndicesToTrackIds(Streams(StreamsWithCoverArt), parsed);
        return MkvmergeCommands.BuildRemuxArgv("mkvmerge", "in.mkv", destination, plan, map, parsed.Attachments);
    }

    [Fact]
    public void The_kept_tracks_are_named_by_mkvmerge_id_and_ordered_video_audio_subtitles()
    {
        var plan = MakePlan([0], [Track(1, "eng", @default: true)], [Subtitle(3, "fre", forced: true)]);

        var argv = Argv(plan);

        Assert.Equal("mkvmerge", argv[0]);
        Assert.Contains("--gui-mode", argv);
        Assert.Equal(["--output", "out.mkv"], argv.SkipWhile(a => a != "--output").Take(2));
        Assert.Equal(["--video-tracks", "0"], argv.SkipWhile(a => a != "--video-tracks").Take(2));
        Assert.Equal(["--audio-tracks", "1"], argv.SkipWhile(a => a != "--audio-tracks").Take(2));
        Assert.Equal(["--subtitle-tracks", "3"], argv.SkipWhile(a => a != "--subtitle-tracks").Take(2));
        Assert.Equal(["--track-order", "0:0,0:1,0:3"], argv.SkipWhile(a => a != "--track-order").Take(2));
        // The source is the last thing before the global track order, as mkvmerge requires.
        Assert.Equal("in.mkv", argv[^3]);
    }

    [Fact]
    public void Keeping_no_subtitles_says_so_because_silence_would_keep_them_all()
    {
        var argv = Argv(MakePlan([0], [Track(1, "eng", @default: true)], []));

        Assert.Contains("--no-subtitles", argv);
        Assert.DoesNotContain("--subtitle-tracks", argv);
    }

    [Fact]
    public void Default_and_forced_flags_are_set_per_track_id()
    {
        var plan = MakePlan(
            [0],
            [Track(1, "eng", @default: true)],
            [Subtitle(2, "eng", @default: true), Subtitle(3, "fre", forced: true)]);

        var argv = Argv(plan);
        var pairs = argv.Zip(argv.Skip(1)).ToList();

        Assert.Contains(("--default-track-flag", "1:yes"), pairs);
        Assert.Contains(("--default-track-flag", "2:yes"), pairs);
        Assert.Contains(("--default-track-flag", "3:no"), pairs);
        Assert.Contains(("--forced-display-flag", "2:no"), pairs);
        Assert.Contains(("--forced-display-flag", "3:yes"), pairs);
    }

    [Fact]
    public void Stale_statistics_tags_need_no_flags_because_mkvmerge_drops_them()
    {
        // The counterpart of FfmpegCommands' explicit "-metadata:s:a:0 DURATION=" clears (#547 item 3):
        // mkvmerge recomputes them, so the argv stays quiet. Guards against someone porting the ffmpeg flags.
        var argv = Argv(MakePlan([0], [Track(1, "eng", @default: true)], []));

        Assert.DoesNotContain(argv, token => token.Contains("DURATION", StringComparison.Ordinal));
        Assert.DoesNotContain(argv, token => token.Contains("_STATISTICS_", StringComparison.Ordinal));
    }

    // --- attachments: RemoveImages and RemoveAttachments stay independent --------------------

    private const string TwoAttachments = """
        {"tracks":[{"id":0,"type":"video"},{"id":1,"type":"audio"},{"id":2,"type":"subtitles"},{"id":3,"type":"subtitles"}],
         "attachments":[{"id":1,"file_name":"cover.jpg","content_type":"image/jpeg"},
                        {"id":2,"file_name":"TestFont.ttf","content_type":"font/ttf"}]}
        """;

    [Fact]
    public void Keeping_everything_says_nothing_about_attachments()
    {
        var argv = Argv(MakePlan([0], [Track(1, "eng")], []), TwoAttachments);

        Assert.DoesNotContain("--no-attachments", argv);
        Assert.DoesNotContain("--attachments", argv);
    }

    [Fact]
    public void Removing_images_keeps_the_font_and_drops_the_cover()
    {
        var plan = MakePlan([0], [Track(1, "eng")], [], new MetadataRules { RemoveImages = true });

        var argv = Argv(plan, TwoAttachments);

        Assert.Equal(["--attachments", "2"], argv.SkipWhile(a => a != "--attachments").Take(2));
    }

    [Fact]
    public void Removing_attachments_keeps_the_cover_and_drops_the_font()
    {
        var plan = MakePlan([0], [Track(1, "eng")], [], new MetadataRules { RemoveAttachments = true });

        var argv = Argv(plan, TwoAttachments);

        Assert.Equal(["--attachments", "1"], argv.SkipWhile(a => a != "--attachments").Take(2));
    }

    [Fact]
    public void Removing_both_drops_every_attachment()
    {
        var plan = MakePlan([0], [Track(1, "eng")], [], new MetadataRules { RemoveImages = true, RemoveAttachments = true });

        var argv = Argv(plan, TwoAttachments);

        Assert.Contains("--no-attachments", argv);
        Assert.DoesNotContain("--attachments", argv);
    }

    [Fact]
    public void Removing_a_kind_the_source_does_not_have_says_nothing()
    {
        // Only a cover here, and only fonts are being removed: nothing to say, and "--attachments 1" would be
        // a no-op that still had to be right.
        var plan = MakePlan([0], [Track(1, "eng")], [], new MetadataRules { RemoveAttachments = true });

        var argv = Argv(plan);

        Assert.DoesNotContain("--no-attachments", argv);
        Assert.DoesNotContain("--attachments", argv);
    }

    // --- the rest of the metadata rules ------------------------------------------------------

    [Fact]
    public void Chapters_tags_and_title_removal_have_their_own_options()
    {
        var plan = MakePlan(
            [0],
            [Track(1, "eng")],
            [],
            new MetadataRules { RemoveChapters = true, RemoveOtherMetadata = true, RemoveTitle = true });

        var argv = Argv(plan);

        Assert.Contains("--no-chapters", argv);
        Assert.Contains("--no-global-tags", argv);
        Assert.Contains("--no-track-tags", argv);
        Assert.Equal(["--title", string.Empty], argv.SkipWhile(a => a != "--title").Take(2));
    }

    [Fact]
    public void Removing_language_tags_sets_every_kept_track_to_undetermined()
    {
        var plan = MakePlan([0], [Track(1, "eng")], [Subtitle(2, "eng")], new MetadataRules { RemoveLanguageTags = true });

        var pairs = Argv(plan).Zip(Argv(plan).Skip(1)).ToList();

        Assert.Contains(("--language", "0:und"), pairs);
        Assert.Contains(("--language", "1:und"), pairs);
        Assert.Contains(("--language", "2:und"), pairs);
    }

    [Fact]
    public void Clearing_video_track_names_writes_an_empty_name()
    {
        var plan = MakePlan([0], [Track(1, "eng")], [], new MetadataRules { ClearVideoTrackNames = true });

        Assert.Equal(["--track-name", "0:"], Argv(plan).SkipWhile(a => a != "--track-name").Take(2));
    }

    // --- container support and progress ------------------------------------------------------

    [Theory]
    [InlineData("out.mkv", true)]
    [InlineData("OUT.MKV", true)]
    // WebM stays on ffmpeg until it gets the same treatment: see the #503 trial's recommendation.
    [InlineData("out.webm", false)]
    [InlineData("out.mp4", false)]
    [InlineData("out", false)]
    public void Only_matroska_is_written_by_mkvmerge(string destination, bool expected) =>
        Assert.Equal(expected, MkvmergeCommands.SupportsDestination(destination));

    [Theory]
    [InlineData("#GUI#progress 26%", 26d)]
    [InlineData("#GUI#progress 100%", 100d)]
    [InlineData("  #GUI#progress 0%  ", 0d)]
    [InlineData("The cue entries (the index) are being written...", null)]
    [InlineData("#GUI#progress not-a-number%", null)]
    [InlineData("", null)]
    public void Progress_is_read_from_gui_mode_lines_only(string line, double? expected) =>
        Assert.Equal(expected, MkvmergeCommands.TryParseProgressPercent(line));
}
