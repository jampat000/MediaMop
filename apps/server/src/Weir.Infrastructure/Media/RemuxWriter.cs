using System.Text.Json;
using Weir.Core.Media;
using Weir.Core.Rules;

namespace Weir.Infrastructure.Media;

/// <summary>
/// Which tool writes a remux (#548). The default stays <see cref="Ffmpeg"/> until the real-sample gate in
/// issue #548 passes — the #503 trial could not obtain Dolby Vision, TrueHD Atmos, PGS or DTS-HD MA media, so
/// mkvmerge's handling of them is still unproven.
/// </summary>
public enum RemuxWriterChoice
{
    /// <summary>ffmpeg writes every container. Today's behaviour, and the default.</summary>
    Ffmpeg,

    /// <summary>mkvmerge writes Matroska when it is installed; ffmpeg writes everything else.</summary>
    Auto,

    /// <summary>mkvmerge writes Matroska; a non-Matroska container still goes to ffmpeg, which is the only tool that can write it.</summary>
    Mkvmerge,
}

/// <summary>One remux to perform, independent of which tool performs it.</summary>
/// <param name="Source">The file to read.</param>
/// <param name="Destination">The staged output to write.</param>
/// <param name="Plan">Which streams to keep and how to tag them.</param>
/// <param name="SourceProbe">The source's own ffprobe JSON, already read by the caller.</param>
/// <param name="ProgressCallback">Reported to as the tool runs, when given.</param>
/// <param name="DurationSeconds">The expected output duration, for the progress percentage only.</param>
/// <param name="Acceleration">The hardware acceleration decision, when one was made. ffmpeg only.</param>
public sealed record RemuxWriteRequest(
    string Source,
    string Destination,
    RemuxPlan Plan,
    JsonElement SourceProbe,
    Action<FfmpegProgressUpdate>? ProgressCallback = null,
    double? DurationSeconds = null,
    AccelerationDecision? Acceleration = null);

/// <summary>
/// Writes the output of one remux pass. Both writers are given the same <see cref="RemuxPlan"/> and produce a
/// file that <see cref="MediaTools.ValidateStagedOutputAsync"/> (#500) then checks in exactly the same way —
/// validation is not part of the writer, so neither tool can grade its own work.
/// </summary>
public interface IRemuxWriter
{
    /// <summary>The tool's name, as the activity log and the system page show it.</summary>
    string Name { get; }

    /// <summary>
    /// True when this writer can write <paramref name="destination"/>'s container and its tool is available.
    /// </summary>
    bool CanWrite(string destination);

    /// <summary>Writes <paramref name="request"/>'s output. Throws on failure; the caller owns cleanup.</summary>
    Task WriteAsync(RemuxWriteRequest request, CancellationToken cancellationToken = default);
}
