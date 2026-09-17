using System.ComponentModel;
using System.Text;
using Microsoft.Extensions.Logging;
using Weir.Core.Media;
using Weir.Core.Rules;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;

namespace Weir.Infrastructure.Tests.Media;

/// <summary>
/// Ports of <c>test_refiner_ffprobe_log_levels.py</c>, <c>test_refiner_remux_mux_validation.py</c>,
/// <c>test_refiner_probe_controls.py</c> (tool resolution) and the detection half of
/// <c>test_refiner_hardware_acceleration.py</c>, with a scripted runner in place of <c>subprocess</c>.
/// </summary>
public sealed class MediaToolsTests : IDisposable
{
    private readonly string _root = Directory.CreateTempSubdirectory("weir-media-tools-").FullName;

    public void Dispose() => Directory.Delete(_root, recursive: true);

    private string WriteFile(string name, byte[] content)
    {
        var path = Path.Combine(_root, name);
        File.WriteAllBytes(path, content);
        return path;
    }

    private static MediaTools Tools(IProcessRunner runner, ListLogger<MediaTools>? logger = null, TimeProvider? time = null) =>
        new(runner, new FixedResolver(), logger ?? new ListLogger<MediaTools>(), time ?? TimeProvider.System);

    // --- ffprobe log levels ----------------------------------------------------------------

    [Fact]
    public async Task Ffprobe_success_diagnostics_are_debug_not_warning()
    {
        var media = WriteFile("movie.mkv", "not-empty"u8.ToArray());
        var logger = new ListLogger<MediaTools>();
        var runner = new ScriptedRunner(_ => new ScriptedRun { Stdout = """{"streams":[]}"""u8.ToArray() });

        await Tools(runner, logger).FfprobeJsonAsync(media);

        Assert.DoesNotContain(logger.Entries, e => e.Level == LogLevel.Warning && e.Message.Contains("REFINER_FFPROBE", StringComparison.Ordinal));
        Assert.Contains(logger.Entries, e => e.Level == LogLevel.Debug && e.Message.Contains("REFINER_FFPROBE_FILE_STATE", StringComparison.Ordinal));
        Assert.Contains(logger.Entries, e => e.Level == LogLevel.Debug && e.Message.Contains("REFINER_FFPROBE_CALL", StringComparison.Ordinal));
        Assert.Contains(logger.Entries, e => e.Level == LogLevel.Debug && e.Message.Contains("REFINER_FFPROBE_RESULT", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Ffprobe_failure_result_still_warns()
    {
        var media = WriteFile("movie.mkv", "not-empty"u8.ToArray());
        var logger = new ListLogger<MediaTools>();
        var runner = new ScriptedRunner(_ => new ScriptedRun { ExitCode = 1, Stderr = "broken"u8.ToArray() });

        var error = await Assert.ThrowsAnyAsync<MediaToolException>(() => Tools(runner, logger).FfprobeJsonAsync(media));

        Assert.Contains("broken", error.Message, StringComparison.Ordinal);
        Assert.Contains(logger.Entries, e => e.Level == LogLevel.Warning && e.Message.Contains("REFINER_FFPROBE_RESULT", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("film.mkv: Invalid data found when processing input", true)]
    [InlineData("EBML header parsing failed", true)]
    [InlineData("film.mkv: Permission denied", false)]
    [InlineData("broken", false)]
    public async Task Only_ffprobe_saying_the_contents_are_unreadable_marks_the_media_bad(string stderr, bool unreadable)
    {
        var media = WriteFile("movie.mkv", new byte[64]);
        var runner = new ScriptedRunner(_ => new ScriptedRun { ExitCode = 1, Stderr = Encoding.UTF8.GetBytes(stderr) });

        var error = await Assert.ThrowsAnyAsync<MediaToolException>(() => Tools(runner).FfprobeJsonAsync(media));

        Assert.Equal(unreadable, error is MediaUnreadableException);
    }

    [Fact]
    public async Task A_missing_or_empty_file_is_not_probed()
    {
        var empty = WriteFile("empty.mkv", []);
        var runner = new ScriptedRunner(_ => new ScriptedRun());

        var missing = await Assert.ThrowsAsync<MediaToolException>(() => Tools(runner).FfprobeJsonAsync(Path.Combine(_root, "gone.mkv")));
        var emptyError = await Assert.ThrowsAsync<MediaToolException>(() => Tools(runner).FfprobeJsonAsync(empty));

        Assert.Equal("file missing or empty at probe time", missing.Message);
        Assert.Equal("file missing or empty at probe time", emptyError.Message);
        Assert.Empty(runner.Requests);
    }

    // --- validation ------------------------------------------------------------------------

    [Fact]
    public async Task Source_integrity_validation_reads_primary_video_to_completion()
    {
        var source = WriteFile("complete.mkv", "complete"u8.ToArray());
        var runner = new ScriptedRunner(_ => new ScriptedRun());

        await Tools(runner).ValidateMediaIntegrityAsync(source);

        var request = Assert.Single(runner.Requests);
        Assert.Equal(
            ["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-err_detect", "explode", "-i", source, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"],
            request.Argv);
    }

    [Fact]
    public async Task Source_integrity_validation_rejects_incomplete_media()
    {
        var source = WriteFile("testament.mkv", "partial"u8.ToArray());
        var runner = new ScriptedRunner(_ => new ScriptedRun { ExitCode = 1, Stderr = "Invalid data found when processing input"u8.ToArray() });

        var error = await Assert.ThrowsAsync<MediaCompletenessException>(() => Tools(runner).ValidateMediaIntegrityAsync(source));

        Assert.Contains("Invalid data found when processing input", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Temp_output_is_deleted_when_duration_validation_fails()
    {
        var source = WriteFile("source.mkv", "source"u8.ToArray());
        var workDir = Path.Combine(_root, "work");
        var plan = new RemuxPlan { VideoIndices = [0], Audio = [new PlannedTrack { InputIndex = 1, LangLabel = "eng", Default = true }], Subtitles = [] };
        var runner = new ScriptedRunner(request => request.Argv[0] == "ffprobe"
            ? new ScriptedRun { Stdout = """{"format": {"duration": "1.0"}, "streams": [{"codec_type": "audio"}]}"""u8.ToArray() }
            : new ScriptedRun());
        var tools = new MediaTools(runner, new FixedResolver(), new ListLogger<MediaTools>(), TimeProvider.System, p => new MediaFileState(p, true, true, 100, 0));

        var error = await Assert.ThrowsAsync<MediaCompletenessException>(() => tools.RemuxToTempFileAsync(source, workDir, plan, durationSeconds: 100.0));

        Assert.Contains("incomplete", error.Message, StringComparison.Ordinal);
        Assert.Empty(Directory.EnumerateFileSystemEntries(workDir));
        var ffmpeg = runner.Requests[0];
        Assert.StartsWith(Path.Combine(Path.GetFullPath(workDir), "source.refiner."), ffmpeg.Argv[^1], StringComparison.Ordinal);
        Assert.EndsWith(".mkv", ffmpeg.Argv[^1], StringComparison.Ordinal);
    }

    [Fact]
    public async Task Progress_run_stops_absurd_projected_runtime_without_piping_stderr()
    {
        var runner = new ScriptedRunner(_ => new ScriptedRun { Lines = ["out_time_ms=1000000", "speed=0.006x", "progress=continue"] });
        var tools = Tools(runner, time: new ScriptedTimeProvider([0.0, 1.0, 2.0, 61.0]));

        var error = await Assert.ThrowsAsync<MediaToolException>(() =>
            tools.RunFfmpegAsync(["ffmpeg", "input.mpg", "output.mpg"], progressCallback: _ => { }, durationSeconds: 72_500.0));

        Assert.Contains("more than 12 hours remaining", error.Message, StringComparison.Ordinal);
        Assert.True(runner.Killed);
        // Only a bounded tail of stderr is kept, never the whole stream.
        Assert.Equal(ProcessOutput.Tail, Assert.Single(runner.Requests).Stderr);
    }

    // --- tool resolution -------------------------------------------------------------------

    [Fact]
    public void Resolve_ffprobe_ffmpeg_uses_explicit_tool_dir()
    {
        var toolDir = Directory.CreateDirectory(Path.Combine(_root, "ffmpeg-tools")).FullName;
        var (probeName, mpegName) = MediaToolLocations.ToolNames(OperatingSystem.IsWindows());
        var ffprobe = WriteFile(Path.Combine("ffmpeg-tools", probeName), []);
        var ffmpeg = WriteFile(Path.Combine("ffmpeg-tools", mpegName), []);
        var resolver = new MediaToolResolver(Path.Combine(_root, "home"), getEnvironmentVariable: name => name == "WEIR_FFMPEG_DIR" ? toolDir : null);

        Assert.Equal((ffprobe, ffmpeg), resolver.Resolve());
    }

    [Fact]
    public void Bundled_tools_under_the_weir_home_are_used_before_path()
    {
        var home = Path.Combine(_root, "home");
        var bundled = Directory.CreateDirectory(Path.Combine(home, "bin", "ffmpeg")).FullName;
        var (probeName, mpegName) = MediaToolLocations.ToolNames(OperatingSystem.IsWindows());
        File.WriteAllBytes(Path.Combine(bundled, probeName), []);
        File.WriteAllBytes(Path.Combine(bundled, mpegName), []);
        var resolver = new MediaToolResolver(home, getEnvironmentVariable: _ => null);

        Assert.Equal((Path.Combine(bundled, probeName), Path.Combine(bundled, mpegName)), resolver.Resolve());
    }

    [Fact]
    public void Missing_tools_say_how_to_provide_them()
    {
        var resolver = new MediaToolResolver(Path.Combine(_root, "home"), getEnvironmentVariable: name => name == "PATH" ? string.Empty : null);

        var error = Assert.Throws<MediaToolException>(() => resolver.Resolve());

        Assert.Equal(MediaToolLocations.MissingToolsMessage, error.Message);
    }

    // --- detection -------------------------------------------------------------------------

    [Fact]
    public async Task Ffmpegs_reported_methods_are_parsed()
    {
        var runner = new ScriptedRunner(_ => new ScriptedRun { Stdout = "Hardware acceleration methods:\ncuda\nvaapi\nqsv\n"u8.ToArray() });

        var report = await Tools(runner).DetectAccelerationAsync("ffmpeg");

        Assert.True(report.Detected);
        Assert.Equal(["cuda", "qsv", "vaapi"], report.AvailableMethods);
        Assert.Equal(["ffmpeg", "-hide_banner", "-hwaccels"], Assert.Single(runner.Requests).Argv);
    }

    [Fact]
    public async Task A_missing_ffmpeg_reports_nothing_rather_than_raising()
    {
        var runner = new ScriptedRunner(_ => new ScriptedRun { Throw = new Win32Exception(2, "no such file") });

        var report = await Tools(runner).DetectAccelerationAsync("ffmpeg");

        Assert.False(report.Detected);
        Assert.Empty(report.AvailableMethods);
        Assert.Contains("could not ask ffmpeg", report.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_failing_ffmpeg_reports_nothing_rather_than_raising()
    {
        var runner = new ScriptedRunner(_ => new ScriptedRun { ExitCode = 1 });

        var report = await Tools(runner).DetectAccelerationAsync("ffmpeg");

        Assert.False(report.Detected);
        Assert.Contains("software decoding", report.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_timeout_reports_nothing_rather_than_raising()
    {
        var runner = new ScriptedRunner(_ => new ScriptedRun { Timeout = ProcessTimeoutKind.Overall, ExitCode = -1 });

        var report = await Tools(runner).DetectAccelerationAsync("ffmpeg");

        Assert.False(report.Detected);
        Assert.Equal(TimeSpan.FromSeconds(10), Assert.Single(runner.Requests).Timeout);
    }
}
