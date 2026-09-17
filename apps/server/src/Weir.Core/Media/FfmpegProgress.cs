using System.Globalization;
using Weir.Core.Rules;

namespace Weir.Core.Media;

/// <summary>One progress report from <c>run_ffmpeg</c> (the dict handed to <c>progress_callback</c>).</summary>
public sealed record FfmpegProgressUpdate
{
    /// <summary>0..99 while running, 100 at the end; null when the duration is unknown.</summary>
    public double? Percent { get; init; }

    public long? EtaSeconds { get; init; }

    public long ElapsedSeconds { get; init; }

    /// <summary><c>out_time_ms</c> in seconds; null when ffmpeg reported something that is not a number.</summary>
    public double? ProcessedSeconds { get; init; }

    public string? Speed { get; init; }

    /// <summary>ffmpeg's own <c>progress=</c> value: <c>continue</c> or <c>end</c>.</summary>
    public required string Progress { get; init; }
}

/// <summary>
/// The line-by-line logic of <c>run_ffmpeg</c>'s progress loop: <c>-progress pipe:1</c> output is
/// <c>key=value</c> lines, and each <c>progress=</c> line closes a block. Time is supplied by the
/// caller as seconds since the process started, read once per line exactly where the reference reads it.
/// </summary>
public sealed class FfmpegProgressTracker
{
    private readonly Dictionary<string, string> _fields = new(StringComparer.Ordinal);
    private readonly double? _durationSeconds;
    private readonly double? _timeoutSeconds;

    public FfmpegProgressTracker(double? durationSeconds, double? timeoutSeconds = FfmpegCommands.FfmpegTimeoutSeconds)
    {
        _durationSeconds = durationSeconds;
        _timeoutSeconds = timeoutSeconds;
    }

    /// <summary>
    /// Feeds one raw stdout line. Returns the update to report, or null. Throws <see cref="MediaToolException"/>
    /// where the reference kills ffmpeg: past the time limit, or projecting more than twelve hours remaining.
    /// </summary>
    public FfmpegProgressUpdate? Feed(string rawLine, double secondsSinceStart)
    {
        ArgumentNullException.ThrowIfNull(rawLine);
        var elapsed = PyMax(0.0, secondsSinceStart);
        if (_timeoutSeconds is { } timeout && elapsed > timeout)
        {
            throw new MediaToolException("ffmpeg timed out");
        }

        var line = Py.Strip(rawLine);
        var equals = line.IndexOf('=', StringComparison.Ordinal);
        if (line.Length == 0 || equals < 0)
        {
            return null;
        }

        var key = line[..equals];
        var value = line[(equals + 1)..];
        _fields[key] = value;
        if (key != "progress")
        {
            return null;
        }

        double? outTime = null;
        var outTimeText = _fields.TryGetValue("out_time_ms", out var ms) ? ms : "0";
        if (Py.TryFloatFromText(outTimeText) is { } micros)
        {
            outTime = PyMax(0.0, micros / 1_000_000.0);
        }

        var ended = value == "end";
        double? percent = null;
        long? eta = null;
        if (_durationSeconds is { } duration && duration != 0 && duration > 0 && outTime is { } processed)
        {
            percent = PyMax(0.0, PyMin(ended ? 100.0 : 99.0, processed / duration * 100.0));
            if (percent > 0 && !ended)
            {
                var totalEstimate = elapsed / (percent.Value / 100.0);
                eta = (long)PyMax(0, PyInt(totalEstimate - elapsed));
            }
        }

        if (ended)
        {
            percent = 100.0;
            eta = 0;
        }

        if (elapsed >= FfmpegCommands.FfmpegSlowGraceSeconds && eta is { } projected && projected > FfmpegCommands.FfmpegMaxProjectedRemainingSeconds)
        {
            throw new MediaToolException(
                "ffmpeg was stopped because progress projected more than 12 hours remaining. "
                + "The input may be malformed, mislabeled, or unreadable at a usable speed.");
        }

        return new FfmpegProgressUpdate
        {
            Percent = percent,
            EtaSeconds = eta,
            ElapsedSeconds = (long)PyInt(elapsed),
            ProcessedSeconds = outTime,
            Speed = _fields.TryGetValue("speed", out var speed) ? speed : null,
            Progress = value,
        };
    }

    /// <summary><c>max(a, b)</c>: the first argument unless the second is strictly greater.</summary>
    private static double PyMax(double a, double b) => b > a ? b : a;

    /// <summary><c>min(a, b)</c>: the first argument unless the second is strictly smaller.</summary>
    private static double PyMin(double a, double b) => b < a ? b : a;

    /// <summary><c>int(float)</c>: truncates; raises where Python raises, or where the result will not fit a long.</summary>
    private static double PyInt(double value)
    {
        if (double.IsNaN(value))
        {
            throw new RulesInputException("ValueError", "cannot convert float NaN to integer");
        }

        if (double.IsInfinity(value))
        {
            throw new RulesInputException("OverflowError", "cannot convert float infinity to integer");
        }

        var truncated = Math.Truncate(value);
        if (truncated is >= 9.2233720368547758e18 or < -9.2233720368547758e18)
        {
            throw new RulesInputException("OverflowError", string.Create(CultureInfo.InvariantCulture, $"{value} is outside the range the .NET port supports"));
        }

        return truncated;
    }
}
