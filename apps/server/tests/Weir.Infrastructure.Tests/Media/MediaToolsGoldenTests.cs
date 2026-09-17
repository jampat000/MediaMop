using System.ComponentModel;
using System.Globalization;
using System.Numerics;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Weir.Core.Media;
using Weir.Core.Rules;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;

namespace Weir.Infrastructure.Tests.Media;

/// <summary>
/// <see cref="MediaTools"/> end to end against the Python reference, with processes and file state replaced by
/// what <c>scripts/generate-ffmpeg-golden.py</c> fed the Python functions: the same log lines at the same levels,
/// the same exception types and messages, the same progress reports and the same detection reports.
/// </summary>
public sealed class MediaToolsGoldenTests
{
    private static readonly string GoldenDirectory = Path.Combine(AppContext.BaseDirectory, "Media", "golden");

    [Fact]
    public async Task Ffprobe_runs_log_and_fail_exactly_as_the_python_layer_does()
    {
        using var document = Load("ffprobe.json");
        var cases = document.RootElement.EnumerateArray().ToList();
        Assert.True(cases.Count >= 30);

        foreach (var item in cases)
        {
            var name = item.GetProperty("name").GetString()!;
            var input = item.GetProperty("input");
            var path = input.GetProperty("path").GetString()!;
            var run = input.GetProperty("run");
            var runner = new ScriptedRunner(request => run.TryGetProperty("timeout", out _)
                ? new ScriptedRun { Timeout = ProcessTimeoutKind.Overall, ExitCode = -1 }
                : new ScriptedRun
                {
                    ExitCode = run.GetProperty("returncode").GetInt32(),
                    Stdout = Encoding.UTF8.GetBytes(run.GetProperty("stdout").GetString()!),
                    Stderr = Encoding.UTF8.GetBytes(run.GetProperty("stderr").GetString()!),
                });
            var state = input.GetProperty("path_state");
            var logger = new ListLogger<MediaTools>();
            var tools = new MediaTools(runner, new FixedResolver(), logger, TimeProvider.System, p => state.ValueKind == JsonValueKind.Null
                ? new MediaFileState(p, true, true, 1234, 1700000000.25)
                : new MediaFileState(
                    p,
                    state.GetProperty("exists").GetBoolean(),
                    state.GetProperty("is_file").GetBoolean(),
                    state.GetProperty("size").GetInt64(),
                    state.GetProperty("mtime").GetDouble()));
            var kwargs = input.GetProperty("kwargs");

            JsonElement? result = null;
            Exception? error = null;
            try
            {
                result = await tools.FfprobeJsonAsync(
                    path,
                    timeoutSeconds: kwargs.TryGetProperty("timeout_s", out var t) ? t.GetInt32() : FfmpegCommands.FfprobeTimeoutSeconds,
                    probeSizeMb: kwargs.TryGetProperty("probe_size_mb", out var ps) ? ps.GetInt32() : 10,
                    analyzeDurationSeconds: kwargs.TryGetProperty("analyze_duration_seconds", out var ad) ? ad.GetInt32() : 10);
            }
            catch (Exception caught) when (caught is MediaToolException or MediaToolTimeoutException)
            {
                error = caught;
            }

            var expected = item.GetProperty("expected");
            if (expected.TryGetProperty("result", out var expectedResult))
            {
                Assert.True(error is null, $"{name}: {error}");
                Assert.True(JsonEquivalent(expectedResult, result!.Value), $"{name}: result {result!.Value.GetRawText()}");
            }
            else
            {
                AssertError(expected.GetProperty("error"), error, name);
            }

            var expectedLogs = expected.GetProperty("logs").EnumerateArray()
                .Select(e => (e.GetProperty("level").GetString()!, e.GetProperty("message").GetString()!))
                .ToList();
            var actualLogs = logger.Entries.Select(e => (e.Level == LogLevel.Warning ? "warning" : "debug", e.Message)).ToList();
            Assert.Equal(expectedLogs, actualLogs);
        }
    }

    [Fact]
    public async Task Quiet_ffmpeg_runs_fail_as_the_python_layer_does()
    {
        using var document = Load("ffmpeg-run.json");
        foreach (var item in document.RootElement.GetProperty("quiet").EnumerateArray())
        {
            var input = item.GetProperty("input");
            var label = input.GetRawText();
            var returnCode = input.GetProperty("returncode");
            var stderr = Convert.FromHexString(input.GetProperty("stderr").GetString()!);
            var runner = new ScriptedRunner(_ => returnCode.ValueKind == JsonValueKind.Null
                ? new ScriptedRun { Timeout = ProcessTimeoutKind.Overall, ExitCode = -1, Stderr = stderr }
                : new ScriptedRun { ExitCode = returnCode.GetInt32(), Stderr = stderr });
            var tools = Tools(runner);
            var timeout = input.GetProperty("timeout_s");
            var argv = new[] { "ffmpeg", "-i", "in.mkv", "out.mkv" };

            var error = await Capture(() => timeout.ValueKind == JsonValueKind.Null
                ? tools.RunFfmpegAsync(argv)
                : tools.RunFfmpegAsync(argv, timeoutSeconds: timeout.GetInt32()));

            AssertOutcome(item.GetProperty("expected"), error, label);
            var request = Assert.Single(runner.Requests);
            Assert.Equal(argv, request.Argv);
            Assert.Equal(ProcessOutput.Tail, request.Stderr);
            Assert.Equal(ProcessInput.Null, request.Stdin);
        }
    }

    [Fact]
    public async Task Progress_runs_report_and_stop_as_the_python_layer_does()
    {
        using var document = Load("ffmpeg-run.json");
        var cases = document.RootElement.GetProperty("progress").EnumerateArray().ToList();
        Assert.NotEmpty(cases);

        foreach (var item in cases)
        {
            var name = item.GetProperty("name").GetString()!;
            var input = item.GetProperty("input");
            var lines = input.GetProperty("lines").EnumerateArray().Select(l => l.GetString()!.TrimEnd('\n').TrimEnd('\r')).ToList();
            var times = input.GetProperty("times").EnumerateArray().Select(t => t.GetDouble()).ToList();
            var rc = input.TryGetProperty("rc", out var rcJson) ? rcJson.GetInt32() : 0;
            var stderr = input.TryGetProperty("stderr", out var stderrJson) ? Encoding.UTF8.GetBytes(stderrJson.GetString()!) : [];
            var runner = new ScriptedRunner(_ => new ScriptedRun { Lines = lines, ExitCode = rc, Stderr = stderr });
            var tools = new MediaTools(runner, new FixedResolver(), new ListLogger<MediaTools>(), new ScriptedTimeProvider(times));
            var duration = input.GetProperty("duration");
            double? durationSeconds = duration.ValueKind == JsonValueKind.Null ? null : duration.GetDouble();
            var updates = new List<FfmpegProgressUpdate>();
            var argv = new[] { "ffmpeg", "-i", "in.mkv", "out.mkv" };

            Exception? error;
            if (input.TryGetProperty("timeout_s", out var timeoutJson))
            {
                int? timeout = timeoutJson.ValueKind == JsonValueKind.Null ? null : timeoutJson.GetInt32();
                error = await Capture(() => tools.RunFfmpegAsync(argv, timeout, updates.Add, durationSeconds));
            }
            else
            {
                error = await Capture(() => tools.RunFfmpegAsync(argv, progressCallback: updates.Add, durationSeconds: durationSeconds));
            }

            var expected = item.GetProperty("expected");
            AssertOutcome(expected, error, name);
            Assert.True(expected.GetProperty("killed").GetBoolean() == runner.Killed, $"{name}: killed");
            var request = Assert.Single(runner.Requests);
            Assert.Equal(["ffmpeg", "-i", "in.mkv", "-progress", "pipe:1", "-nostats", "out.mkv"], request.Argv);
            Assert.Equal(ProcessOutput.Tail, request.Stderr);

            var expectedUpdates = expected.GetProperty("updates").EnumerateArray().ToList();
            Assert.True(expectedUpdates.Count == updates.Count, $"{name}: {updates.Count} updates");
            for (var i = 0; i < updates.Count; i++)
            {
                var e = expectedUpdates[i];
                var a = updates[i];
                var label = $"{name} update {i}";
                Assert.True(ReprOrNull(e.GetProperty("percent")) == (a.Percent is null ? null : PythonText.FloatRepr(a.Percent.Value)), $"{label}: percent {a.Percent}");
                Assert.True(ReprOrNull(e.GetProperty("processed_seconds")) == (a.ProcessedSeconds is null ? null : PythonText.FloatRepr(a.ProcessedSeconds.Value)), $"{label}: processed");
                Assert.True((e.GetProperty("eta_seconds").ValueKind == JsonValueKind.Null ? null : e.GetProperty("eta_seconds").GetInt64()) == a.EtaSeconds, $"{label}: eta {a.EtaSeconds}");
                Assert.True(e.GetProperty("elapsed_seconds").GetInt64() == a.ElapsedSeconds, $"{label}: elapsed");
                Assert.True(ReprOrNull(e.GetProperty("speed")) == a.Speed, $"{label}: speed");
                Assert.True(e.GetProperty("progress").GetString() == a.Progress, $"{label}: progress");
            }
        }
    }

    [Fact]
    public async Task Hardware_detection_matches_the_python_layer_including_failures()
    {
        using var document = Load("hardware.json");
        foreach (var item in document.RootElement.GetProperty("detection").EnumerateArray())
        {
            var name = item.GetProperty("name").GetString()!;
            var input = item.GetProperty("input");
            var runner = new ScriptedRunner(_ => input.TryGetProperty("raise", out var raise)
                ? raise.GetString() == "oserror"
                    ? new ScriptedRun { Throw = new Win32Exception(2, "no such file") }
                    : new ScriptedRun { Timeout = ProcessTimeoutKind.Overall, ExitCode = -1 }
                : new ScriptedRun
                {
                    ExitCode = input.GetProperty("returncode").GetInt32(),
                    Stdout = Encoding.UTF8.GetBytes(input.GetProperty("stdout").GetString()!),
                });

            var report = await Tools(runner).DetectAccelerationAsync("ffmpeg");

            var expected = item.GetProperty("expected");
            Assert.Equal(Strings(expected.GetProperty("argv")), Assert.Single(runner.Requests).Argv);
            var expectedReport = expected.GetProperty("report");
            Assert.True(Strings(expectedReport.GetProperty("available_methods")).SequenceEqual(report.AvailableMethods), name);
            Assert.True(expectedReport.GetProperty("detected").GetBoolean() == report.Detected, name);
            Assert.Equal(expectedReport.GetProperty("detail").GetString(), report.Detail);
            Assert.True(Strings(expectedReport.GetProperty("vendors")).SequenceEqual(report.Vendors), name);
        }
    }

    [Fact]
    public async Task Integrity_checks_fail_as_the_python_layer_does()
    {
        using var document = Load("validation.json");
        foreach (var item in document.RootElement.GetProperty("integrity").EnumerateArray())
        {
            var input = item.GetProperty("input");
            var runner = new ScriptedRunner(_ => new ScriptedRun
            {
                ExitCode = input.GetProperty("returncode").GetInt32(),
                Stderr = Encoding.UTF8.GetBytes(input.GetProperty("stderr").GetString()!),
            });

            var error = await Capture(() => Tools(runner).ValidateMediaIntegrityAsync("in.mkv"));

            AssertOutcome(item.GetProperty("expected"), error, input.GetRawText());
            var request = Assert.Single(runner.Requests);
            Assert.Equal(ProcessOutput.Discard, request.Stdout);
            Assert.Equal(ProcessInput.Null, request.Stdin);
        }
    }

    [Fact]
    public async Task Remux_output_validation_through_ffprobe_matches_the_python_layer()
    {
        using var document = Load("validation.json");
        foreach (var item in document.RootElement.GetProperty("remux_output").EnumerateArray())
        {
            var name = item.GetProperty("name").GetString()!;
            var input = item.GetProperty("input");
            var runner = new ScriptedRunner(_ => new ScriptedRun { Stdout = Encoding.UTF8.GetBytes(input.GetProperty("probe").GetString()!) });
            var durationText = input.GetProperty("expected_duration_seconds");
            double? expectedDuration = durationText.ValueKind == JsonValueKind.Null
                ? null
                : double.Parse(durationText.GetString()!, NumberStyles.Float, CultureInfo.InvariantCulture);

            var error = await Capture(() => Tools(runner).ValidateRemuxOutputAsync("out.mkv", input.GetProperty("expected_audio").GetInt32(), expectedDuration));

            AssertOutcome(item.GetProperty("expected"), error, name);
        }
    }

    // --- helpers ---------------------------------------------------------------------------

    private static MediaTools Tools(IProcessRunner runner) =>
        new(runner, new FixedResolver(), new ListLogger<MediaTools>(), TimeProvider.System, p => new MediaFileState(p, true, true, 1234, 1700000000.25));

    private static async Task<Exception?> Capture(Func<Task> action)
    {
        try
        {
            await action();
            return null;
        }
        catch (Exception error) when (error is MediaToolException or MediaToolTimeoutException or RulesInputException)
        {
            return error;
        }
    }

    private static void AssertOutcome(JsonElement expected, Exception? actual, string label)
    {
        if (expected.TryGetProperty("error", out var error))
        {
            AssertError(error, actual, label);
        }
        else
        {
            Assert.True(actual is null, $"{label}: expected success, got {actual}");
        }
    }

    private static void AssertError(JsonElement expected, Exception? actual, string label)
    {
        Assert.True(actual is not null, $"{label}: expected {expected.GetRawText()}, got success");
        var type = actual switch
        {
            MediaUnreadableException => "MediaUnreadableError",
            MediaCompletenessException => "MediaCompletenessError",
            MediaToolException => "RuntimeError",
            MediaToolTimeoutException => "TimeoutExpired",
            RulesInputException rules => rules.PythonError,
            _ => actual.GetType().Name,
        };
        Assert.True(expected.GetProperty("type").GetString() == type, $"{label}: expected {expected.GetRawText()}, got {type}: {actual.Message}");
        if (actual is not RulesInputException)
        {
            Assert.Equal(expected.GetProperty("message").GetString(), actual.Message);
        }
    }

    private static string? ReprOrNull(JsonElement value) => value.ValueKind == JsonValueKind.Null ? null : value.GetString();

    private static List<string> Strings(JsonElement array) => array.EnumerateArray().Select(e => e.GetString()!).ToList();

    /// <summary>Equal as Python sees parsed JSON: same keys in the same order, numbers by value.</summary>
    private static bool JsonEquivalent(JsonElement expected, JsonElement actual)
    {
        if (expected.ValueKind != actual.ValueKind)
        {
            return false;
        }

        switch (expected.ValueKind)
        {
            case JsonValueKind.Object:
                var e = expected.EnumerateObject().ToList();
                var a = actual.EnumerateObject().ToList();
                return e.Count == a.Count && e.Zip(a).All(pair => pair.First.Name == pair.Second.Name && JsonEquivalent(pair.First.Value, pair.Second.Value));
            case JsonValueKind.Array:
                var ea = expected.EnumerateArray().ToList();
                var aa = actual.EnumerateArray().ToList();
                return ea.Count == aa.Count && ea.Zip(aa).All(pair => JsonEquivalent(pair.First, pair.Second));
            case JsonValueKind.String:
                return expected.GetString() == actual.GetString();
            case JsonValueKind.Number:
                var er = expected.GetRawText();
                var ar = actual.GetRawText();
                return er.AsSpan().IndexOfAny('.', 'e', 'E') < 0 && ar.AsSpan().IndexOfAny('.', 'e', 'E') < 0
                    ? BigInteger.Parse(er, CultureInfo.InvariantCulture) == BigInteger.Parse(ar, CultureInfo.InvariantCulture)
                    : expected.GetDouble() == actual.GetDouble();
            default:
                return true;
        }
    }

    private static JsonDocument Load(string fileName) => JsonDocument.Parse(File.ReadAllText(Path.Combine(GoldenDirectory, fileName)));
}
