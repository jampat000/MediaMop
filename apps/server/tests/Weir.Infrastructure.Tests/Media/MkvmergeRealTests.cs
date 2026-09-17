using System.Text.Json;
using Weir.Core.Media;
using Weir.Core.Rules;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;

namespace Weir.Infrastructure.Tests.Media;

/// <summary>
/// Issue #548 against the real mkvmerge, on tiny files generated at test time. These prove the things a golden
/// argv test cannot: that mkvmerge accepts the argv Weir builds, that what comes out is what the plan asked
/// for, and that it passes #500's output validation — the same validation the ffmpeg writer's output passes,
/// run by the caller so neither writer grades its own work.
/// </summary>
public sealed class MkvmergeRealTests : IDisposable
{
    private readonly string _root = Directory.CreateTempSubdirectory("weir-real-mkvmerge-").FullName;

    public void Dispose() => Directory.Delete(_root, recursive: true);

    private static MediaTools Tools() =>
        new(new ProcessRunner(), new RealResolver(), new ListLogger<MediaTools>(), TimeProvider.System);

    private sealed class RealResolver : IMediaToolResolver
    {
        public (string Ffprobe, string Ffmpeg) Resolve() => RealFfmpeg.Tools!.Value;

        public string? ResolveMkvmerge() => RealMkvmerge.Tool;
    }

    private static MkvmergeRemuxWriter Writer(MediaTools tools) => new(tools, new RealResolver());

    /// <summary>Three seconds: mpeg4 video, English and French AAC tracks, English and French SubRip tracks.</summary>
    private async Task<string> GenerateFixtureAsync(string name = "fixture.mkv")
    {
        var english = Path.Combine(_root, "en.srt");
        var french = Path.Combine(_root, "fr.srt");
        await File.WriteAllTextAsync(english, "1\n00:00:00,000 --> 00:00:02,000\nEnglish line\n").ConfigureAwait(false);
        await File.WriteAllTextAsync(french, "1\n00:00:00,000 --> 00:00:02,000\nLigne francaise\n").ConfigureAwait(false);
        var path = Path.Combine(_root, name);
        string[] argv =
        [
            RealFfmpeg.Tools!.Value.Ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
            "-i", english, "-i", french,
            "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s", "-map", "4:s",
            "-c:v", "mpeg4", "-c:a", "aac", "-c:s", "srt",
            "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=fre",
            "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=fre",
            path,
        ];
        await RunAsync(argv).ConfigureAwait(false);
        return path;
    }

    /// <summary>
    /// The same fixture with attachments added by mkvmerge itself: a <c>cover.jpg</c>, which Matroska stores as
    /// an attachment and ffprobe reports as an extra video stream flagged <c>attached_pic</c>, and a font, which
    /// it does not. This is the shape measured on a real library file.
    /// </summary>
    private async Task<string> GenerateFixtureWithAttachmentsAsync()
    {
        var plain = await GenerateFixtureAsync("plain.mkv").ConfigureAwait(false);
        var cover = Path.Combine(_root, "cover.jpg");
        await RunAsync([
            RealFfmpeg.Tools!.Value.Ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=120x120:d=1", "-frames:v", "1", cover,
        ]).ConfigureAwait(false);
        var font = Path.Combine(_root, "TestFont.ttf");
        await File.WriteAllTextAsync(font, "not really a font, but an attachment that is not cover art").ConfigureAwait(false);
        var path = Path.Combine(_root, "attached.mkv");
        await RunAsync([
            RealMkvmerge.Tool!, "--output", path,
            // These describe the *next* --attach-file, so the order matters.
            "--attachment-mime-type", "image/jpeg", "--attachment-name", "cover.jpg", "--attach-file", cover,
            "--attachment-mime-type", "font/ttf", "--attachment-name", "TestFont.ttf", "--attach-file", font,
            plain,
        ]).ConfigureAwait(false);
        return path;
    }

    private static async Task RunAsync(string[] argv)
    {
        var result = await new ProcessRunner().RunAsync(
            new ProcessRequest
            {
                Argv = argv,
                Timeout = TimeSpan.FromSeconds(120),
                Stdin = ProcessInput.Null,
                Stdout = ProcessOutput.Discard,
                Stderr = ProcessOutput.Tail,
                TailBytes = 8192,
            },
            CancellationToken.None).ConfigureAwait(false);
        // mkvmerge's 1 is "succeeded with warnings".
        Assert.True(result.ExitCode is 0 or 1, $"{argv[0]} exited {result.ExitCode}: {ProbeOutput.TailText(result.Stderr)}");
    }

    private static IReadOnlyList<JsonElement> Streams(JsonElement probe, string codecType) =>
        [.. probe.GetProperty("streams").EnumerateArray().Where(s => s.GetProperty("codec_type").GetString() == codecType)];

    private static string? Language(JsonElement stream) =>
        stream.TryGetProperty("tags", out var tags) && tags.TryGetProperty("language", out var language)
            ? language.GetString()
            : null;

    private static RemuxPlan EnglishOnlyPlan(JsonElement probe, MetadataRules? metadata = null)
    {
        var config = RemuxRules.DefaultConfig() with
        {
            PrimaryAudioLang = "eng",
            SecondaryAudioLang = string.Empty,
            TertiaryAudioLang = string.Empty,
            SubtitleMode = RemuxRuleValues.SubtitleModeKeepSelected,
            SubtitleLangs = ["eng"],
            Metadata = metadata ?? new MetadataRules(),
        };
        var split = RemuxRules.SplitStreams(new ProbeResult(probe));
        var plan = RemuxRules.PlanRemux(split.Video, split.Audio, split.Subtitles, config);
        Assert.NotNull(plan);
        return plan;
    }

    // --- identification ----------------------------------------------------------------------

    [RequiresMkvmergeFact]
    public async Task Cover_art_is_an_attachment_to_mkvmerge_and_a_stream_to_ffprobe()
    {
        var fixture = await GenerateFixtureWithAttachmentsAsync();
        var tools = Tools();

        var probe = await tools.FfprobeJsonAsync(fixture);
        var identification = await tools.IdentifyMkvmergeAsync(RealMkvmerge.Tool!, fixture);

        // ffprobe reports seven streams: the five real tracks, the cover as a second "video" stream flagged
        // attached_pic, and the font as an "attachment" stream. Neither of the last two is a track to mkvmerge.
        Assert.Equal(7, probe.GetProperty("streams").GetArrayLength());
        Assert.Equal(2, Streams(probe, "video").Count);
        Assert.Single(Streams(probe, "attachment"));
        // mkvmerge: 5 tracks and 2 attachments, the cover among the latter.
        Assert.Equal(5, identification.Tracks.Count);
        Assert.Equal(2, identification.Attachments.Count);
        Assert.Contains(identification.Attachments, a => a.IsCoverArt && a.FileName == "cover.jpg");
        Assert.Contains(identification.Attachments, a => !a.IsCoverArt && a.FileName == "TestFont.ttf");
    }

    [RequiresMkvmergeFact]
    public async Task The_track_mapping_skips_the_cover_and_still_lines_up()
    {
        var fixture = await GenerateFixtureWithAttachmentsAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var identification = await tools.IdentifyMkvmergeAsync(RealMkvmerge.Tool!, fixture);
        var streams = probe.GetProperty("streams").EnumerateArray().Select(s => new ProbeStreamInfo(s)).ToList();

        var map = MkvmergeCommands.MapStreamIndicesToTrackIds(streams, identification);

        Assert.Equal(new Dictionary<int, int> { [0] = 0, [1] = 1, [2] = 2, [3] = 3, [4] = 4 }, map);
    }

    // --- writing -----------------------------------------------------------------------------

    [RequiresMkvmergeFact]
    public async Task Mkvmerge_writes_the_plan_and_the_output_passes_the_same_validation_ffmpeg_output_does()
    {
        var fixture = await GenerateFixtureAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var plan = EnglishOnlyPlan(probe);
        Assert.Single(plan.Audio);
        Assert.Single(plan.Subtitles);
        var sourceWarnings = await tools.ProbeWarningLinesAsync(fixture);
        var updates = new List<FfmpegProgressUpdate>();

        // ValidateStagedOutputAsync (#500) runs inside this call: it not throwing is half the assertion.
        var output = await tools.RemuxToTempFileAsync(
            fixture,
            Path.Combine(_root, "work"),
            plan,
            probe,
            sourceWarnings,
            updates.Add,
            ProbeOutput.DurationSeconds(probe),
            writer: Writer(tools));

        var outputProbe = await tools.FfprobeJsonAsync(output);
        Assert.Equal("eng", Language(Assert.Single(Streams(outputProbe, "audio"))));
        Assert.Equal("eng", Language(Assert.Single(Streams(outputProbe, "subtitle"))));
        Assert.Single(Streams(outputProbe, "video"));
        Assert.NotEmpty(updates);
        Assert.Equal(100.0, updates[^1].Percent);
        Assert.Equal("end", updates[^1].Progress);
    }

    [RequiresMkvmergeFact]
    public async Task Kept_cover_art_hands_the_write_back_to_ffmpeg()
    {
        // The default: RemoveImages is off, so the planner keeps the cover in VideoIndices as a video stream to
        // map. mkvmerge would write it as the attachment it really is, which #500's positional validation reads
        // as the wrong shape — so ffmpeg writes this one and the output is exactly today's.
        var fixture = await GenerateFixtureWithAttachmentsAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var plan = EnglishOnlyPlan(probe);
        Assert.Equal(2, plan.VideoIndices.Count);

        var output = await tools.RemuxToTempFileAsync(
            fixture,
            Path.Combine(_root, "work-attached"),
            plan,
            probe,
            await tools.ProbeWarningLinesAsync(fixture),
            writer: Writer(tools));

        // ffmpeg's shape: the cover is an output video stream, and #547's attachment map kept the font.
        var outputProbe = await tools.FfprobeJsonAsync(output);
        Assert.Equal(2, Streams(outputProbe, "video").Count);
        Assert.Single(Streams(outputProbe, "attachment"));
    }

    [RequiresMkvmergeFact]
    public async Task The_refusal_is_specific_so_only_this_case_falls_back()
    {
        var fixture = await GenerateFixtureWithAttachmentsAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var plan = EnglishOnlyPlan(probe);

        var error = await Assert.ThrowsAsync<MkvmergeUnsupportedPlanException>(
            () => Writer(tools).WriteAsync(new RemuxWriteRequest(fixture, Path.Combine(_root, "direct.mkv"), plan, probe)));

        Assert.Contains("cover art", error.Message, StringComparison.Ordinal);
    }

    [RequiresMkvmergeFact]
    public async Task Removing_images_lets_mkvmerge_write_it_and_drops_the_cover()
    {
        var fixture = await GenerateFixtureWithAttachmentsAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var plan = EnglishOnlyPlan(probe, new MetadataRules { RemoveImages = true });
        // With the images dropped the plan keeps only the real video track, which mkvmerge can address.
        Assert.Single(plan.VideoIndices);

        var output = await tools.RemuxToTempFileAsync(
            fixture,
            Path.Combine(_root, "work-no-images"),
            plan,
            probe,
            await tools.ProbeWarningLinesAsync(fixture),
            writer: Writer(tools));

        var identification = await tools.IdentifyMkvmergeAsync(RealMkvmerge.Tool!, output);
        var kept = Assert.Single(identification.Attachments);
        Assert.Equal("TestFont.ttf", kept.FileName);
    }

    [RequiresMkvmergeFact]
    public async Task Removing_images_and_attachments_leaves_neither()
    {
        var fixture = await GenerateFixtureWithAttachmentsAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var plan = EnglishOnlyPlan(probe, new MetadataRules { RemoveImages = true, RemoveAttachments = true });

        var output = await tools.RemuxToTempFileAsync(
            fixture,
            Path.Combine(_root, "work-bare"),
            plan,
            probe,
            await tools.ProbeWarningLinesAsync(fixture),
            writer: Writer(tools));

        var identification = await tools.IdentifyMkvmergeAsync(RealMkvmerge.Tool!, output);
        Assert.Empty(identification.Attachments);
    }

    [RequiresMkvmergeFact]
    public async Task Turning_the_rewrite_off_lets_the_failure_through()
    {
        // The advanced escape hatch: with the rewrite disabled, a file mkvmerge cannot express fails instead of
        // being written by ffmpeg. Proves the fallback in the test above is the setting doing its job and not
        // something that happens regardless.
        var fixture = await GenerateFixtureWithAttachmentsAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var plan = EnglishOnlyPlan(probe);

        await Assert.ThrowsAsync<MkvmergeUnsupportedPlanException>(
            () => tools.RemuxToTempFileAsync(
                fixture,
                Path.Combine(_root, "work-no-rewrite"),
                plan,
                probe,
                [],
                writer: Writer(tools),
                rewriteWithFfmpegOnFailure: false));
    }

    // --- writer selection ---------------------------------------------------------------------

    [RequiresMkvmergeFact]
    public void Mkvmerge_takes_matroska_and_leaves_every_other_container_to_ffmpeg()
    {
        var writer = Writer(Tools());

        Assert.True(writer.CanWrite("out.mkv"));
        Assert.False(writer.CanWrite("out.mp4"));
        // WebM stays with ffmpeg: see the #503 trial's recommendation.
        Assert.False(writer.CanWrite("out.webm"));
    }
}
