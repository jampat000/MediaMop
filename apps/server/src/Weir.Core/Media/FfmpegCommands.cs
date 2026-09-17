using System.Globalization;
using Weir.Core.Rules;

namespace Weir.Core.Media;

/// <summary>
/// The ffprobe and ffmpeg command lines from <c>refiner_remux_mux.py</c>, token for token. Paths are
/// taken as the strings the caller already holds (the reference passes <c>str(path)</c>).
/// </summary>
public static class FfmpegCommands
{
    /// <summary><c>REFINER_FFMPEG_TIMEOUT_S</c>: the wall-clock limit for one ffmpeg run.</summary>
    public const int FfmpegTimeoutSeconds = 3600;

    /// <summary><c>REFINER_FFMPEG_SLOW_GRACE_S</c>: projections are ignored for the first minute.</summary>
    public const int FfmpegSlowGraceSeconds = 60;

    /// <summary><c>REFINER_FFMPEG_MAX_PROJECTED_REMAINING_S</c>: twelve hours.</summary>
    public const int FfmpegMaxProjectedRemainingSeconds = 12 * 60 * 60;

    /// <summary>ffprobe's default time limit in <c>ffprobe_json</c>.</summary>
    public const int FfprobeTimeoutSeconds = 120;

    /// <summary><c>_REFINER_FFPROBE_LOG_MAX_CHARS</c>.</summary>
    public const int ProbeLogMaxChars = 2000;

    /// <summary><c>_REFINER_FFMPEG_STDERR_TAIL_BYTES</c>: how much of ffmpeg's stderr a failure message keeps.</summary>
    public const int FfmpegStderrTailBytes = 32 * 1024;

    /// <summary>The ffmpeg wait after its progress stream closes (<c>proc.wait(timeout=5)</c>).</summary>
    public const int ProgressExitWaitSeconds = 5;

    /// <summary><c>_HWACCEL_TIMEOUT_SECONDS</c> (a float in the reference, so it prints as <c>10.0</c>).</summary>
    public const double HwaccelTimeoutSeconds = 10.0;

    /// <summary><c>build_ffprobe_argv</c>: probe size and analyze duration are clamped to 1..1024 MB and 1..300 s.</summary>
    public static IReadOnlyList<string> BuildFfprobeArgv(string ffprobeBin, string src, long probeSizeMb = 10, long analyzeDurationSeconds = 10)
    {
        ArgumentNullException.ThrowIfNull(ffprobeBin);
        ArgumentNullException.ThrowIfNull(src);
        var psMb = Math.Max(1, Math.Min(1024, probeSizeMb));
        var adS = Math.Max(1, Math.Min(300, analyzeDurationSeconds));
        return
        [
            ffprobeBin,
            "-v",
            "quiet",
            "-probesize",
            (psMb * 1024 * 1024).ToString(CultureInfo.InvariantCulture),
            "-analyzeduration",
            (adS * 1_000_000).ToString(CultureInfo.InvariantCulture),
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            src,
        ];
    }

    /// <summary>The full demux of the primary video that <c>validate_media_integrity</c> runs.</summary>
    public static IReadOnlyList<string> BuildIntegrityArgv(string ffmpegBin, string path)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        ArgumentNullException.ThrowIfNull(path);
        return
        [
            ffmpegBin,
            "-hide_banner",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-i",
            path,
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "null",
            "-",
        ];
    }

    /// <summary>What <c>detect_acceleration</c> asks ffmpeg.</summary>
    public static IReadOnlyList<string> BuildHwaccelsArgv(string ffmpegBin)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        return [ffmpegBin, "-hide_banner", "-hwaccels"];
    }

    /// <summary>
    /// <c>build_ffmpeg_argv</c>. <paramref name="inputFlags"/> (hardware acceleration and strictness) go
    /// before <c>-i</c>, because <c>-hwaccel</c> applies to the input that follows it.
    /// </summary>
    public static IReadOnlyList<string> BuildRemuxArgv(string ffmpegBin, string src, string dst, RemuxPlan plan, IReadOnlyList<string>? inputFlags = null)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        ArgumentNullException.ThrowIfNull(src);
        ArgumentNullException.ThrowIfNull(dst);
        ArgumentNullException.ThrowIfNull(plan);
        var args = new List<string>
        {
            ffmpegBin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-nostdin",
            "-y",
        };
        args.AddRange(inputFlags ?? []);
        args.AddRange(["-i", src]);
        foreach (var vi in plan.VideoIndices)
        {
            args.AddRange(["-map", Map(vi)]);
        }

        foreach (var track in plan.Audio)
        {
            args.AddRange(["-map", Map(track.InputIndex)]);
        }

        foreach (var track in plan.Subtitles)
        {
            args.AddRange(["-map", Map(track.InputIndex)]);
        }

        args.AddRange(["-c", "copy"]);
        // After the maps: the maps decide which streams exist, these decide what they carry.
        args.AddRange(MetadataStreams.ArgvFlags(plan.Metadata));
        for (var i = 0; i < plan.Audio.Count; i++)
        {
            args.AddRange([$"-disposition:a:{i.ToString(CultureInfo.InvariantCulture)}", plan.Audio[i].Default ? "default" : "0"]);
        }

        for (var i = 0; i < plan.Subtitles.Count; i++)
        {
            var track = plan.Subtitles[i];
            var flags = new List<string>();
            if (track.Default)
            {
                flags.Add("default");
            }

            if (track.Forced)
            {
                flags.Add("forced");
            }

            args.AddRange([$"-disposition:s:{i.ToString(CultureInfo.InvariantCulture)}", flags.Count > 0 ? string.Join('+', flags) : "0"]);
        }

        args.Add(dst);
        return args;
    }

    /// <summary><c>_argv_with_progress</c>: <c>-progress pipe:1 -nostats</c> goes just before the output path.</summary>
    public static IReadOnlyList<string> WithProgress(IReadOnlyList<string> argv)
    {
        ArgumentNullException.ThrowIfNull(argv);
        var insertAt = argv.Count > 1 ? argv.Count - 1 : argv.Count;
        var result = new List<string>(argv.Count + 3);
        result.AddRange(argv.Take(insertAt));
        result.AddRange(["-progress", "pipe:1", "-nostats"]);
        result.AddRange(argv.Skip(insertAt));
        return result;
    }

    /// <summary><c>logger.debug("Refiner: ffmpeg %s", " ".join(argv[:8]) + " ...")</c>.</summary>
    public static string DebugSummary(IReadOnlyList<string> argv)
    {
        ArgumentNullException.ThrowIfNull(argv);
        return "Refiner: ffmpeg " + string.Join(' ', argv.Take(8)) + " ...";
    }

    private static string Map(int index) => "0:" + index.ToString(CultureInfo.InvariantCulture);
}
