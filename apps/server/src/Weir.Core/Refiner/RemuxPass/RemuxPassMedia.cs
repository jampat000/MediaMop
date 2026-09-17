using System.Text.Json;
using Weir.Core.Json;
using Weir.Core.Rules;

namespace Weir.Core.Refiner.RemuxPass;

/// <summary>What a pass reads off the probe beyond the plan (helpers of <c>run.py</c> and <c>refiner_runner_units.py</c>).</summary>
public static class RemuxPassMedia
{
    /// <summary><c>str(value or "")</c>.</summary>
    public static string TruthyText(JsonElement? value) => Py.Truthy(value) ? Py.Str(value) : string.Empty;

    /// <summary><c>int(value or 0)</c> inside <c>try/except (TypeError, ValueError)</c> returning 0.</summary>
    public static long IntegerOrZero(JsonElement? value) => Py.Truthy(value) && Py.TryInt(value, out var parsed) ? parsed : 0;

    /// <summary><c>video_dimensions_from_streams</c>: (width, height) of the largest video stream, by <c>width</c>/<c>coded_width</c>.</summary>
    public static (long? Width, long? Height) VideoDimensions(IReadOnlyList<ProbeStreamInfo> videoStreams) =>
        (LargestDimension(videoStreams, "width", "coded_width"), LargestDimension(videoStreams, "height", "coded_height"));

    private static long? LargestDimension(IReadOnlyList<ProbeStreamInfo> streams, params string[] keys)
    {
        long? largest = null;
        foreach (var stream in streams)
        {
            foreach (var key in keys)
            {
                if (!Py.TryInt(stream.Get(key), out var value))
                {
                    continue;
                }

                if (value > 0)
                {
                    largest = largest is null ? value : Math.Max(largest.Value, value);
                    break;
                }
            }
        }

        return largest;
    }

    /// <summary><c>_probe_duration_seconds</c>: the longest positive duration among the format and the streams.</summary>
    public static double? ProbeDurationSeconds(ProbeResult probe)
    {
        ArgumentNullException.ThrowIfNull(probe);
        var candidates = new List<double>();
        if (probe.Json.ValueKind == JsonValueKind.Object && Py.Get(probe.Json, "format") is { ValueKind: JsonValueKind.Object } format)
        {
            AddFloat(candidates, Py.Get(format, "duration"));
        }

        foreach (var stream in probe.Streams)
        {
            AddFloat(candidates, stream.Get("duration"));
        }

        var valid = candidates.Where(value => value > 0).ToList();
        return valid.Count > 0 ? valid.Max() : null;
    }

    /// <summary><c>float(value or 0)</c> inside <c>contextlib.suppress(TypeError, ValueError)</c>.</summary>
    private static void AddFloat(List<double> candidates, JsonElement? value)
    {
        if (!Py.Truthy(value))
        {
            candidates.Add(0);
            return;
        }

        var element = value!.Value;
        switch (element.ValueKind)
        {
            case JsonValueKind.Number:
                candidates.Add(element.GetDouble());
                break;
            case JsonValueKind.True:
                candidates.Add(1);
                break;
            case JsonValueKind.String when Py.TryFloatFromText(element.GetString()!) is { } parsed:
                candidates.Add(parsed);
                break;
        }
    }

    /// <summary><c>_video_bit_depth</c>: <c>bits_per_raw_sample</c>, else read from the pixel format, else null.</summary>
    public static long? VideoBitDepth(ProbeStreamInfo stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        var raw = stream.Get("bits_per_raw_sample");
        if (raw is { } element && element.ValueKind is JsonValueKind.String or JsonValueKind.Number)
        {
            var text = PyStrings.Strip(Py.Str(raw));
            if (text.Length > 0 && text.All(char.IsAsciiDigit) && Py.TryInt(raw, out var bits) && bits > 0)
            {
                return bits;
            }
        }

        var pixelFormat = TruthyText(stream.Get("pix_fmt")).ToLowerInvariant();
        if (pixelFormat.Length == 0)
        {
            return null;
        }

        foreach (var depth in new[] { 12, 10 })
        {
            if (pixelFormat.Contains($"{depth}le", StringComparison.Ordinal) || pixelFormat.Contains($"{depth}be", StringComparison.Ordinal) ||
                pixelFormat.EndsWith($"p{depth}", StringComparison.Ordinal))
            {
                return depth;
            }
        }

        return 8;
    }

    /// <summary>
    /// <c>_pass_through_plan</c>: an unchanged file described without applying any rules. Observability only; pass-through
    /// never runs ffmpeg.
    /// </summary>
    public static RemuxPlan PassThroughPlan(IReadOnlyList<ProbeStreamInfo> video, IReadOnlyList<ProbeStreamInfo> audio, IReadOnlyList<ProbeStreamInfo> subtitles)
    {
        ArgumentNullException.ThrowIfNull(video);
        ArgumentNullException.ThrowIfNull(audio);
        ArgumentNullException.ThrowIfNull(subtitles);
        return new RemuxPlan
        {
            VideoIndices = [.. video.Select(stream => (int)IntegerOrZero(stream.Get("index")))],
            Audio = [.. audio.Select(stream => new PlannedTrack
            {
                InputIndex = (int)IntegerOrZero(stream.Get("index")),
                LangLabel = Language(stream),
                Forced = Flag(stream, "forced"),
                Default = Flag(stream, "default"),
                Channels = (int)IntegerOrZero(stream.Get("channels")),
                Bitrate = IntegerOrZero(stream.Get("bit_rate")),
                CodecName = TruthyText(stream.Get("codec_name")),
                Kind = TrackKind.Audio,
            })],
            Subtitles = [.. subtitles.Select(stream => new PlannedTrack
            {
                InputIndex = (int)IntegerOrZero(stream.Get("index")),
                LangLabel = Language(stream),
                Forced = Flag(stream, "forced"),
                Default = Flag(stream, "default"),
                Kind = TrackKind.Subtitle,
            })],
            AudioSelectionNotes = ["The operator chose Pass through unchanged, so every stream was preserved."],
        };
    }

    private static string Language(ProbeStreamInfo stream)
    {
        if (stream.Get("tags") is { ValueKind: JsonValueKind.Object } tags && Py.Get(tags, "language") is { } language && Py.Truthy(language))
        {
            return Py.Str(language);
        }

        return "und";
    }

    private static bool Flag(ProbeStreamInfo stream, string name) =>
        stream.Get("disposition") is { ValueKind: JsonValueKind.Object } disposition && Py.Truthy(Py.Get(disposition, name));
}
