using System.Globalization;
using System.IO.Pipes;
using System.Text.Json;
using Weir.Core.Media;
using Weir.Core.Rules;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;

namespace Weir.Infrastructure.Tests.Media;

/// <summary>A fact that runs only where ffprobe and ffmpeg can be found (WEIR_FFMPEG_DIR or PATH).</summary>
[AttributeUsage(AttributeTargets.Method)]
public sealed class RequiresFfmpegFactAttribute : FactAttribute
{
    public RequiresFfmpegFactAttribute()
    {
        if (RealFfmpeg.Tools is null)
        {
            Skip = "ffprobe and ffmpeg were not found: set WEIR_FFMPEG_DIR or put them on PATH to run the real-ffmpeg tests.";
        }
    }
}

internal static class RealFfmpeg
{
    public static readonly (string Ffprobe, string Ffmpeg)? Tools = Find();

    private static (string, string)? Find()
    {
        try
        {
            return new MediaToolResolver(Path.Combine(Path.GetTempPath(), "weir-no-home-" + Guid.NewGuid().ToString("N"))).Resolve();
        }
        catch (MediaToolException)
        {
            return null;
        }
    }
}

/// <summary>
/// The ffmpeg layer against real ffprobe and ffmpeg on tiny files generated with <c>-f lavfi</c> at test time:
/// probing, a remux that drops an audio track, validation, truncation and unreadable input. These assert what the
/// Python reference does with the same tools, including where that is not what one would want.
/// </summary>
public sealed class RealFfmpegTests : IDisposable
{
    private readonly string _root = Directory.CreateTempSubdirectory("weir-real-ffmpeg-").FullName;

    public void Dispose() => Directory.Delete(_root, recursive: true);

    private static MediaTools Tools() =>
        new(new ProcessRunner(), new StaticResolver(), new ListLogger<MediaTools>(), TimeProvider.System);

    /// <summary>Three seconds: mpeg4 video, English and French AAC tracks.</summary>
    private async Task<string> GenerateFixtureAsync(string name = "fixture.mkv", params string[] extra)
    {
        var path = Path.Combine(_root, name);
        string[] argv =
        [
            RealFfmpeg.Tools!.Value.Ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
            "-map", "0", "-map", "1", "-map", "2",
            "-c:v", "mpeg4", "-c:a", "aac",
            "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=fre",
            .. extra,
            path,
        ];
        var result = await new ProcessRunner().RunAsync(new ProcessRequest { Argv = argv, Timeout = TimeSpan.FromMinutes(1) });
        Assert.True(result.ExitCode == 0, "fixture generation failed: " + ProbeOutput.TailText(result.Stderr));
        return path;
    }

    private static List<JsonElement> Streams(JsonElement probe, string codecType) =>
        probe.GetProperty("streams").EnumerateArray().Where(s => s.GetProperty("codec_type").GetString() == codecType).ToList();

    [RequiresFfmpegFact]
    public async Task Probe_reads_streams_and_duration()
    {
        var fixture = await GenerateFixtureAsync();

        var probe = await Tools().FfprobeJsonAsync(fixture);

        Assert.Single(Streams(probe, "video"));
        var audio = Streams(probe, "audio");
        Assert.Equal(["eng", "fre"], audio.Select(s => s.GetProperty("tags").GetProperty("language").GetString()));
        var duration = ProbeOutput.DurationSeconds(probe);
        Assert.NotNull(duration);
        Assert.InRange(duration.Value, 2.9, 3.2);
    }

    [RequiresFfmpegFact]
    public async Task A_remux_drops_an_audio_track_reports_progress_and_validates()
    {
        var fixture = await GenerateFixtureAsync();
        var tools = Tools();
        var probe = await tools.FfprobeJsonAsync(fixture);
        var config = RemuxRules.DefaultConfig() with { PrimaryAudioLang = "eng", SecondaryAudioLang = string.Empty, TertiaryAudioLang = string.Empty };
        var split = RemuxRules.SplitStreams(new ProbeResult(probe));
        var plan = RemuxRules.PlanRemux(split.Video, split.Audio, split.Subtitles, config);
        Assert.NotNull(plan);
        Assert.Single(plan.Audio);
        var updates = new List<FfmpegProgressUpdate>();
        var workDir = Path.Combine(_root, "work");

        var output = await tools.RemuxToTempFileAsync(fixture, workDir, plan, updates.Add, ProbeOutput.DurationSeconds(probe));

        Assert.StartsWith(Path.Combine(Path.GetFullPath(workDir), "fixture.refiner."), output, StringComparison.Ordinal);
        var outputProbe = await tools.FfprobeJsonAsync(output);
        var audio = Assert.Single(Streams(outputProbe, "audio"));
        Assert.Equal("eng", audio.GetProperty("tags").GetProperty("language").GetString());
        Assert.Single(Streams(outputProbe, "video"));
        Assert.NotEmpty(updates);
        Assert.Equal("end", updates[^1].Progress);
        Assert.Equal(100.0, updates[^1].Percent);
    }

    [RequiresFfmpegFact]
    public async Task Complete_media_passes_both_validations()
    {
        var fixture = await GenerateFixtureAsync();
        var tools = Tools();

        await tools.ValidateRemuxOutputAsync(fixture, expectedAudio: 2, expectedDurationSeconds: 3.0);
        await tools.ValidateMediaIntegrityAsync(fixture);
    }

    [RequiresFfmpegFact]
    public async Task Output_shorter_than_expected_is_rejected_as_incomplete()
    {
        var fixture = await GenerateFixtureAsync("short.mkv", "-t", "1");

        var error = await Assert.ThrowsAsync<MediaCompletenessException>(() => Tools().ValidateRemuxOutputAsync(fixture, expectedAudio: 2, expectedDurationSeconds: 30.0));

        Assert.Contains("of 30.0s expected", error.Message, StringComparison.Ordinal);
    }

    [RequiresFfmpegFact]
    public async Task A_truncated_download_fails_the_integrity_read()
    {
        // Moov first, so the header survives and only the media data is cut off.
        var fixture = await GenerateFixtureAsync("fixture.mp4", "-movflags", "+faststart");
        var bytes = await File.ReadAllBytesAsync(fixture);
        var truncated = Path.Combine(_root, "truncated.mp4");
        await File.WriteAllBytesAsync(truncated, bytes[..(bytes.Length / 2)]);

        var error = await Assert.ThrowsAsync<MediaCompletenessException>(() => Tools().ValidateMediaIntegrityAsync(truncated));

        Assert.Contains("could not read this media file from start to finish", error.Message, StringComparison.Ordinal);
    }

    [RequiresFfmpegFact]
    public async Task A_truncated_matroska_file_passes_the_duration_check_as_in_the_reference()
    {
        // Parity, not approval: Matroska keeps its duration in the header, so a file cut in half still reports the
        // full length and passes the staged-output check. This is exactly why #539 item 3 fixes the *integrity*
        // read (the next test) rather than this one: the header cannot be trusted, only a full demux can.
        var fixture = await GenerateFixtureAsync();
        var bytes = await File.ReadAllBytesAsync(fixture);
        var truncated = Path.Combine(_root, "truncated.mkv");
        await File.WriteAllBytesAsync(truncated, bytes[..(bytes.Length / 2)]);

        await Tools().ValidateRemuxOutputAsync(truncated, expectedAudio: 2, expectedDurationSeconds: 3.0);
    }

    [RequiresFfmpegFact]
    public async Task A_truncated_matroska_file_fails_the_fixed_integrity_read()
    {
        // #539 item 3: fixed, not parity. The reference's validate_media_integrity only looks at ffmpeg's exit
        // code; this build's ffmpeg exits 0 from the full demux of a file cut in half, only warning "File ended
        // prematurely", so the reference would call this file complete. ValidateMediaIntegrityAsync now treats
        // that warning as failure (Weir.Core.Media.ProbeOutput.IntegrityIncompleteMarkers).
        var fixture = await GenerateFixtureAsync();
        var bytes = await File.ReadAllBytesAsync(fixture);
        var truncated = Path.Combine(_root, "truncated.mkv");
        await File.WriteAllBytesAsync(truncated, bytes[..(bytes.Length / 2)]);

        var error = await Assert.ThrowsAsync<MediaCompletenessException>(() => Tools().ValidateMediaIntegrityAsync(truncated, expectedDurationSeconds: 3.0));

        Assert.Contains("could not read this media file from start to finish", error.Message, StringComparison.Ordinal);
    }

    [RequiresFfmpegFact]
    public async Task Garbage_input_is_classified_unreadable_now_that_ffprobe_runs_with_v_error()
    {
        // #539 item 1: fixed, not parity. The reference probes with "-v quiet", so ffprobe never prints the
        // words the unreadable-media markers look for and this comes back as a plain RuntimeError instead of
        // MediaUnreadableError; "-v error" (Weir.Core.Media.FfmpegCommands.BuildFfprobeArgv) puts them on stderr.
        var garbage = Path.Combine(_root, "garbage.mkv");
        await File.WriteAllBytesAsync(garbage, Enumerable.Range(1, 4096).Select(i => (byte)(i * 37 % 256)).ToArray());

        var error = await Assert.ThrowsAsync<MediaUnreadableException>(() => Tools().FfprobeJsonAsync(garbage));

        Assert.Contains("Invalid data found when processing input", error.Message, StringComparison.Ordinal);
    }

    [RequiresFfmpegFact]
    public async Task A_zero_filled_mkv_is_classified_unreadable()
    {
        // #539: the exact repro from issue #494 (a 10 GB all-zero .mkv on the Deluno rig, reported completed with
        // a copy of itself as output). One megabyte is enough for ffprobe to hit the header immediately.
        var zeroFilled = Path.Combine(_root, "zero-filled.mkv");
        await File.WriteAllBytesAsync(zeroFilled, new byte[1024 * 1024]);

        var error = await Assert.ThrowsAsync<MediaUnreadableException>(() => Tools().FfprobeJsonAsync(zeroFilled));

        Assert.Contains("EBML header parsing failed", error.Message, StringComparison.Ordinal);
    }

    [RequiresFfmpegFact]
    public async Task Hardware_detection_reads_the_real_build()
    {
        var report = await Tools().DetectAccelerationAsync(RealFfmpeg.Tools!.Value.Ffmpeg);

        Assert.True(report.Detected);
        Assert.Equal(report.AvailableMethods.Order(StringComparer.Ordinal), report.AvailableMethods);
        Assert.All(report.AvailableMethods, method => Assert.Matches("^[a-z0-9_]+$", method));
    }

    [RequiresFfmpegFact]
    public async Task A_progress_run_past_its_time_limit_is_stopped()
    {
        var output = Path.Combine(_root, "slow.mkv");
        string[] argv =
        [
            RealFfmpeg.Tools!.Value.Ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-re", "-f", "lavfi", "-i", "testsrc=duration=60:size=160x120:rate=10", "-c:v", "mpeg4",
            output,
        ];
        var started = DateTime.UtcNow;

        var error = await Assert.ThrowsAsync<MediaToolException>(() => Tools().RunFfmpegAsync(argv, timeoutSeconds: 1, progressCallback: _ => { }, durationSeconds: 60));

        Assert.Equal("ffmpeg timed out", error.Message);
        Assert.True(DateTime.UtcNow - started < TimeSpan.FromSeconds(15), string.Create(CultureInfo.InvariantCulture, $"took {DateTime.UtcNow - started}"));
    }

    [RequiresFfmpegFact]
    public async Task A_progress_run_that_never_writes_a_line_is_still_stopped_by_the_timer()
    {
        // #539 item 4: the reference's progress loop only checks its timeout as a line arrives ("for raw in
        // proc.stdout: ..."), so a process stuck reading its input - one that never gets to write a progress line
        // at all - would hang forever. ProcessRunner's timeout is a wall-clock timer instead (see
        // ProcessRunnerTests for the same guarantee without a real ffmpeg), so this is enforced even though
        // nothing is ever read. A Windows named pipe with no writer makes ffmpeg block inside avformat_open_input,
        // before it can emit anything.
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        var pipeName = "weir-hang-" + Guid.NewGuid().ToString("N");
        using var pipeServer = new NamedPipeServerStream(pipeName, PipeDirection.Out);
        string[] argv =
        [
            RealFfmpeg.Tools!.Value.Ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", @"\\.\pipe\" + pipeName, "-c", "copy", Path.Combine(_root, "hang.mkv"),
        ];
        var updates = new List<FfmpegProgressUpdate>();
        var started = DateTime.UtcNow;

        var error = await Assert.ThrowsAsync<MediaToolException>(() => Tools().RunFfmpegAsync(argv, timeoutSeconds: 2, progressCallback: updates.Add));

        Assert.Equal("ffmpeg timed out", error.Message);
        Assert.Empty(updates);
        Assert.True(DateTime.UtcNow - started < TimeSpan.FromSeconds(15), string.Create(CultureInfo.InvariantCulture, $"took {DateTime.UtcNow - started}"));
    }

    private sealed class StaticResolver : IMediaToolResolver
    {
        public (string Ffprobe, string Ffmpeg) Resolve() => RealFfmpeg.Tools!.Value;
    }
}
