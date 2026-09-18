namespace Weir.Core.Media;

/// <summary>
/// #548: how one external media tool's presence is described to an operator, as a pure function of what the
/// tool printed. Both <c>ffmpeg -version</c> and <c>mkvmerge --version</c> answer with a one-line banner
/// followed (for ffmpeg) by its build configuration, so the report is that first line and nothing else —
/// "ffmpeg version 8.0 …", "mkvmerge v102.0 ('…') 64-bit".
/// </summary>
public static class MediaToolVersions
{
    /// <summary>
    /// What an absent tool reports. mkvmerge is optional by design (<see cref="RemuxWriterChoice"/> falls back
    /// to ffmpeg when it is missing), so "not installed" is a fact about this install, never an error —
    /// <c>GET /api/v1/system/media-tools</c> still answers 200 with it.
    /// </summary>
    public const string NotInstalled = "not installed";

    /// <summary>
    /// What a tool that is on disk but would not say what it is reports: it exited non-zero, timed out, or
    /// printed nothing. Deliberately distinct from <see cref="NotInstalled"/> — "the file is there but broken"
    /// and "there is no file" need different fixes, and collapsing them would send an operator looking in the
    /// wrong place.
    /// </summary>
    public const string Unknown = "unknown";

    /// <summary>
    /// How much of the banner line is kept. Long enough for the longest real banner seen (ffmpeg's carries the
    /// distributor's build tag, e.g. "ffmpeg version 8.0-full_build-www.gyan.dev Copyright (c) 2000-2025 the
    /// FFmpeg developers"), short enough that a tool that ignores the flag and streams something unexpected
    /// cannot put an unbounded string into an API response.
    /// </summary>
    public const int MaxLength = 200;

    /// <summary>
    /// The version line from a finished <c>--version</c> run, or <see cref="Unknown"/> when there is nothing
    /// usable to report. <paramref name="exitCode"/> is checked first: ffmpeg and mkvmerge both exit 0 for
    /// <c>--version</c>, so a non-zero exit means the output (if any) is not a banner.
    /// </summary>
    public static string FromBanner(int exitCode, string output)
    {
        ArgumentNullException.ThrowIfNull(output);
        if (exitCode != 0)
        {
            return Unknown;
        }

        foreach (var line in output.Split('\n'))
        {
            var trimmed = line.Trim();
            if (trimmed.Length == 0)
            {
                continue;
            }

            return trimmed.Length > MaxLength ? trimmed[..MaxLength] : trimmed;
        }

        return Unknown;
    }
}

/// <summary>
/// #548: what <c>GET /api/v1/system/media-tools</c> reports. Each value is either a version banner line,
/// <see cref="MediaToolVersions.NotInstalled"/> or <see cref="MediaToolVersions.Unknown"/>.
/// </summary>
/// <param name="Ffmpeg">ffmpeg, which Weir requires — a missing one is why nothing can be processed.</param>
/// <param name="Mkvmerge">mkvmerge, which Weir only prefers — a missing one costs the mkvmerge writer, nothing else.</param>
public sealed record MediaToolVersionReport(string Ffmpeg, string Mkvmerge);
