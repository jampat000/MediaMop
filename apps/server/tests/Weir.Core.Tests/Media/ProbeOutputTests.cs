using System.Text.Json;
using Weir.Core.Media;

namespace Weir.Core.Tests.Media;

/// <summary>
/// Ports of the pure assertions in <c>test_processing_remux_mux_validation.py</c>, <c>test_processing_probe_controls.py</c>
/// and <c>test_processing_ffprobe_log_levels.py</c>: staged-output duration checks, the integrity command line and
/// failure, probe controls, unreadable-media classification and the twelve-hour projection stop.
/// </summary>
public sealed class ProbeOutputTests
{
    private static JsonElement Probe(double duration, int audio = 1)
    {
        var text = duration.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
        var streams = new List<string> { $$"""{"codec_type": "video", "duration": "{{text}}"}""" };
        streams.AddRange(Enumerable.Repeat($$"""{"codec_type": "audio", "duration": "{{text}}"}""", audio));
        using var document = JsonDocument.Parse($$"""{"format": {"duration": "{{text}}"}, "streams": [{{string.Join(", ", streams)}}]}""");
        return document.RootElement.Clone();
    }

    [Fact]
    public void Staged_output_is_rejected_when_its_duration_is_only_a_partial_download()
    {
        var error = Assert.Throws<MediaCompletenessException>(() => ProbeOutput.ValidateRemuxOutput(Probe(212.546), 1, 5384.046));

        Assert.Contains("212.5s of 5384.0s expected", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Staged_output_accepts_normal_duration_rounding() =>
        ProbeOutput.ValidateRemuxOutput(Probe(5379.0), 1, 5384.046);

    [Fact]
    public void Source_integrity_validation_reads_primary_video_to_completion()
    {
        var source = Path.Combine(Path.GetTempPath(), "complete.mkv");

        Assert.Equal(
            ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-err_detect", "explode", "-i", source, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"],
            FfmpegCommands.BuildIntegrityArgv("ffmpeg", source));
    }

    [Fact]
    public void Source_integrity_validation_rejects_incomplete_media()
    {
        var error = ProbeOutput.IntegrityFailure("Invalid data found when processing input");

        Assert.IsType<MediaCompletenessException>(error);
        Assert.Contains("Invalid data found when processing input", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Progress_run_stops_absurd_projected_runtime()
    {
        // The Python test's clock: started at 0, then one reading per line at 1, 2 and 61 seconds.
        var tracker = new FfmpegProgressTracker(durationSeconds: 72_500.0);
        Assert.Null(tracker.Feed("out_time_ms=1000000\n", 1.0));
        Assert.Null(tracker.Feed("speed=0.006x\n", 2.0));

        var error = Assert.Throws<MediaToolException>(() => tracker.Feed("progress=continue\n", 61.0));

        Assert.Contains("more than 12 hours remaining", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Build_ffprobe_argv_includes_probe_controls()
    {
        var argv = FfmpegCommands.BuildFfprobeArgv("ffprobe-x", "/tmp/sample.mkv", probeSizeMb: 25, analyzeDurationSeconds: 14);

        Assert.Contains("-probesize", argv);
        Assert.Contains("-analyzeduration", argv);
        Assert.Equal((25 * 1024 * 1024).ToString(System.Globalization.CultureInfo.InvariantCulture), argv[IndexOf(argv, "-probesize") + 1]);
        Assert.Equal((14 * 1_000_000).ToString(System.Globalization.CultureInfo.InvariantCulture), argv[IndexOf(argv, "-analyzeduration") + 1]);
    }

    [Fact]
    public void Build_ffprobe_argv_clamps_out_of_range_controls()
    {
        var argv = FfmpegCommands.BuildFfprobeArgv("ffprobe-x", "/tmp/sample.mkv", probeSizeMb: 9999, analyzeDurationSeconds: 0);

        Assert.Equal((1024 * 1024 * 1024).ToString(System.Globalization.CultureInfo.InvariantCulture), argv[IndexOf(argv, "-probesize") + 1]);
        Assert.Equal(1_000_000.ToString(System.Globalization.CultureInfo.InvariantCulture), argv[IndexOf(argv, "-analyzeduration") + 1]);
    }

    [Theory]
    [InlineData("film.mkv: Invalid data found when processing input", true)]
    [InlineData("EBML header parsing failed", true)]
    [InlineData("film.mkv: Permission denied", false)]
    [InlineData("broken", false)]
    public void Only_ffprobe_saying_the_contents_are_unreadable_marks_the_media_bad(string stderr, bool unreadable)
    {
        var error = Assert.ThrowsAny<MediaToolException>(() => ProbeOutput.Interpret(1, string.Empty, stderr));

        Assert.Equal(unreadable, error is MediaUnreadableException);
    }

    [Fact]
    public void A_failure_says_what_ffprobe_said()
    {
        var error = Assert.ThrowsAny<MediaToolException>(() => ProbeOutput.Interpret(1, string.Empty, "broken"));

        Assert.Equal("broken", error.Message);
    }

    private static int IndexOf(IReadOnlyList<string> argv, string token) => argv.ToList().IndexOf(token);
}
