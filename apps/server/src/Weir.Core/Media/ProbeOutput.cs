using System.Globalization;
using System.Numerics;
using System.Text.Json;
using Weir.Core.Rules;

namespace Weir.Core.Media;

/// <summary>
/// What <c>ffprobe_json</c>, <c>validate_remux_output</c>, <c>validate_media_integrity</c> and
/// <c>_probe_duration_seconds</c> decide once a tool has run: which failures mean the media is
/// unreadable, what counts as usable output, and when staged output is incomplete.
/// </summary>
public static class ProbeOutput
{
    /// <summary>ffprobe's own words for "this is not readable media" (<c>_UNREADABLE_MEDIA_MARKERS</c>).</summary>
    public static IReadOnlyList<string> UnreadableMediaMarkers { get; } =
    [
        "invalid data found when processing input",
        "ebml header parsing failed",
        "moov atom not found",
        "could not find codec parameters",
        "end of file",
    ];

    /// <summary>
    /// The error <c>ffprobe_json</c> raises for a non-zero exit: <see cref="MediaUnreadableException"/>
    /// when the message carries an unreadable-media marker, otherwise <see cref="MediaToolException"/>.
    /// </summary>
    public static MediaToolException FailureFor(string? stdout, string? stderr)
    {
        var chosen = !string.IsNullOrEmpty(stderr) ? stderr : !string.IsNullOrEmpty(stdout) ? stdout : string.Empty;
        var message = Py.Strip(chosen);
        if (message.Length == 0)
        {
            message = "ffprobe failed";
        }

        var lowered = Py.Lower(message);
        return UnreadableMediaMarkers.Any(marker => lowered.Contains(marker, StringComparison.Ordinal))
            ? new MediaUnreadableException(message)
            : new MediaToolException(message);
    }

    /// <summary>
    /// Everything <c>ffprobe_json</c> does after ffprobe exits: raise for a failure, otherwise parse stdout
    /// and require a JSON object. The returned element is detached from any document.
    /// </summary>
    public static JsonElement Interpret(int returnCode, string? stdout, string? stderr)
    {
        if (returnCode != 0)
        {
            throw FailureFor(stdout, stderr);
        }

        const string Invalid = "ffprobe returned invalid or empty output";
        if (stdout is null || Py.Strip(stdout).Length == 0)
        {
            throw new MediaToolException(Invalid);
        }

        try
        {
            using var document = JsonDocument.Parse(stdout);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new MediaToolException(Invalid);
            }

            return document.RootElement.Clone();
        }
        catch (JsonException error)
        {
            throw new MediaToolException(Invalid, error);
        }
    }

    /// <summary>
    /// <c>_probe_duration_seconds</c>: the longest positive duration among the format and the streams, or null.
    /// </summary>
    public static double? DurationSeconds(JsonElement data)
    {
        var candidates = new List<double>();
        if (data.ValueKind == JsonValueKind.Object)
        {
            var format = Py.Get(data, "format");
            if (Py.IsDict(format) && TryFloatOrZero(Py.Get(format!.Value, "duration"), out var formatDuration))
            {
                candidates.Add(formatDuration);
            }

            var streams = Py.Get(data, "streams");
            if (Py.IsList(streams))
            {
                foreach (var stream in streams!.Value.EnumerateArray())
                {
                    if (stream.ValueKind == JsonValueKind.Object && TryFloatOrZero(Py.Get(stream, "duration"), out var streamDuration))
                    {
                        candidates.Add(streamDuration);
                    }
                }
            }
        }

        double? best = null;
        foreach (var duration in candidates)
        {
            // Python's max() keeps the first of equals and never picks a NaN, which "> 0" already excluded.
            if (duration > 0 && (best is null || duration > best.Value))
            {
                best = duration;
            }
        }

        return best;
    }

    /// <summary>
    /// The checks <c>validate_remux_output</c> makes on the staged output's probe: at least one audio stream,
    /// the expected audio count, and a duration no shorter than expected less max(5 s, 1%).
    /// </summary>
    public static void ValidateRemuxOutput(JsonElement data, int expectedAudio = 0, double? expectedDurationSeconds = null)
    {
        var streamsValue = data.ValueKind == JsonValueKind.Object ? Py.Get(data, "streams") : null;
        if (Py.Truthy(streamsValue) && !Py.IsList(streamsValue))
        {
            throw new MediaToolException("validation failed: invalid ffprobe output");
        }

        var audioCount = 0;
        if (Py.IsList(streamsValue))
        {
            foreach (var stream in streamsValue!.Value.EnumerateArray())
            {
                if (stream.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                var codecType = Py.Get(stream, "codec_type");
                if (!Py.Truthy(codecType))
                {
                    continue;
                }

                if (!Py.IsStr(codecType))
                {
                    // (s.get("codec_type") or "").lower() on a truthy non-string.
                    throw new RulesInputException("AttributeError", "codec_type has no lower()");
                }

                if (Py.Lower(codecType!.Value.GetString()!) == "audio")
                {
                    audioCount++;
                }
            }
        }

        if (audioCount < 1)
        {
            throw new MediaToolException("validation failed: output has no audio stream");
        }

        if (expectedAudio > 0 && audioCount != expectedAudio)
        {
            throw new MediaToolException(
                $"validation failed: expected {expectedAudio.ToString(CultureInfo.InvariantCulture)} audio stream(s), got {audioCount.ToString(CultureInfo.InvariantCulture)}");
        }

        if (expectedDurationSeconds is { } expected && expected > 0)
        {
            var outputDuration = DurationSeconds(data);
            if (outputDuration is null)
            {
                throw new MediaCompletenessException(
                    "Validation failed: Refiner could not confirm the staged output duration, so it was not published.");
            }

            var tolerance = Math.Max(5.0, expected * 0.01);
            if (outputDuration.Value < expected - tolerance)
            {
                throw new MediaCompletenessException(
                    "Validation failed: the staged output is incomplete "
                    + $"({PyText.FormatFixed(outputDuration.Value, 1)}s of {PyText.FormatFixed(expected, 1)}s expected), so it was not published.");
            }
        }
    }

    /// <summary>The error <c>validate_media_integrity</c> raises when the full demux exits non-zero.</summary>
    public static MediaCompletenessException IntegrityFailure(string? stderr)
    {
        var detail = Py.Strip(stderr ?? string.Empty);
        detail = PyText.Clip(detail, FfmpegCommands.ProbeLogMaxChars);
        return new MediaCompletenessException(
            "Weir could not read this media file from start to finish. It may still be downloading or may be "
            + $"incomplete, so Refiner will wait. The media check reported: {(detail.Length > 0 ? detail : "incomplete media data")}.");
    }

    /// <summary>The error <c>run_ffmpeg</c> raises for a non-zero exit, from the tail of stderr.</summary>
    public static MediaToolException FfmpegFailure(string stderrTail) =>
        new(stderrTail.Length > 0 ? stderrTail : "ffmpeg failed");

    /// <summary><c>_read_tail_text</c>: the last bytes of stderr, decoded with replacement and stripped.</summary>
    public static string TailText(ReadOnlySpan<byte> bytes, int maxBytes = FfmpegCommands.FfmpegStderrTailBytes)
    {
        var tail = bytes.Length > maxBytes ? bytes[^maxBytes..] : bytes;
        return Py.Strip(PyText.DecodeUtf8(tail));
    }

    /// <summary>Output captured with <c>text=True, encoding="utf-8", errors="replace"</c>.</summary>
    public static string CapturedText(ReadOnlySpan<byte> bytes) => PyText.TranslateNewlines(PyText.DecodeUtf8(bytes));

    /// <summary><c>str(subprocess.TimeoutExpired)</c> for a timeout given in whole seconds.</summary>
    public static string TimeoutMessage(IEnumerable<string> argv, int timeoutSeconds) =>
        PyText.TimeoutExpiredMessage(argv, timeoutSeconds.ToString(CultureInfo.InvariantCulture));

    /// <summary><c>str(subprocess.TimeoutExpired)</c> for a timeout given as a Python float.</summary>
    public static string TimeoutMessage(IEnumerable<string> argv, double timeoutSeconds) =>
        PyText.TimeoutExpiredMessage(argv, Py.FloatRepr(timeoutSeconds));

    // --- log payloads ------------------------------------------------------------------

    /// <summary>The <c>REFINER_FFPROBE_FILE_STATE</c> JSON.</summary>
    public static string FileStateLogPayload(string path, string resolvedPath, bool exists, bool isFile, long sizeBytes, string suffix, double mtimeEpoch) =>
        new PyJsonObject()
            .Add("path", path)
            .Add("resolved_path", resolvedPath)
            .Add("exists", exists)
            .Add("is_file", isFile)
            .Add("size_bytes", sizeBytes)
            .Add("suffix", PyText.Clip(suffix, 64))
            .Add("mtime_epoch", mtimeEpoch)
            .ToString();

    /// <summary>The <c>REFINER_FFPROBE_CALL</c> JSON.</summary>
    public static string CallLogPayload(string path, IEnumerable<string> argv) =>
        new PyJsonObject()
            .Add("path", path)
            .Add("argv", argv.Select(a => PyText.Clip(a, 256)))
            .ToString();

    /// <summary>The <c>REFINER_FFPROBE_RESULT</c> JSON.</summary>
    public static string ResultLogPayload(string path, int returnCode, string stdout, string stderr) =>
        new PyJsonObject()
            .Add("path", path)
            .Add("returncode", returnCode)
            .Add("stdout", PyText.Clip(stdout, FfmpegCommands.ProbeLogMaxChars))
            .Add("stderr", PyText.Clip(stderr, FfmpegCommands.ProbeLogMaxChars))
            .ToString();

    /// <summary>
    /// <c>float(value or 0)</c> with <c>TypeError</c>/<c>ValueError</c> suppressed (false). An integer too
    /// large for a float raises <c>OverflowError</c> in the reference, which is not suppressed.
    /// </summary>
    private static bool TryFloatOrZero(JsonElement? value, out double result)
    {
        result = 0;
        if (!Py.Truthy(value))
        {
            return true;
        }

        var v = value!.Value;
        switch (v.ValueKind)
        {
            case JsonValueKind.True:
                result = 1.0;
                return true;
            case JsonValueKind.String:
                var parsed = Py.TryFloatFromText(v.GetString()!);
                result = parsed ?? 0;
                return parsed is not null;
            case JsonValueKind.Number:
                var raw = v.GetRawText();
                if (raw.AsSpan().IndexOfAny('.', 'e', 'E') >= 0)
                {
                    result = double.Parse(raw, NumberStyles.Float, CultureInfo.InvariantCulture);
                    return true;
                }

                var integer = BigInteger.Parse(raw, CultureInfo.InvariantCulture);
                result = (double)integer;
                if (double.IsInfinity(result))
                {
                    throw new RulesInputException("OverflowError", "int too large to convert to float");
                }

                return true;
            default:
                return false;
        }
    }
}
