namespace Weir.Core.Media;

/// <summary>
/// #548: which tool writes a library's output. Kept as text like the other mode settings
/// (<see cref="HardwareAcceleration.ModeOff"/> and friends) so it round-trips through SQLite and JSON
/// unchanged.
/// <para>
/// There are deliberately <b>two</b> values, not the three the issue first sketched
/// (<c>auto</c>/<c>ffmpeg</c>/<c>mkvmerge</c>). "mkvmerge" and "auto" would do the identical thing: mkvmerge
/// can only write Matroska, so a non-Matroska container goes to ffmpeg under either, and offering a choice
/// that is not a choice makes the setting impossible to explain honestly. Two values, two behaviours.
/// </para>
/// </summary>
public static class RemuxWriterChoice
{
    /// <summary>
    /// The best tool for each container: mkvmerge for Matroska when it is installed, ffmpeg for everything
    /// else. The default.
    /// <para>
    /// This is the default rather than <see cref="Ffmpeg"/> because it cannot be worse. A write that fails to
    /// run, or whose output fails #500's validation, is rewritten by ffmpeg and validated again
    /// (<c>RewriteWithFfmpeg</c>), so the result matches or beats what ffmpeg alone would have produced. On
    /// Matroska it beats it: mkvmerge keeps attachments and disposition flags by default, drops stale
    /// per-track statistics tags, and can author editions and ordered chapters, none of which ffmpeg's CLI
    /// does without help — see docs/trials/503-mkvmerge-vs-ffmpeg.md.
    /// </para>
    /// </summary>
    public const string Best = "best";

    /// <summary>
    /// ffmpeg writes every container. What every Weir before #548 did, and the escape hatch for anyone who
    /// would rather run one tool than two.
    /// </summary>
    public const string Ffmpeg = "ffmpeg";

    public static IReadOnlyList<string> All { get; } = [Best, Ffmpeg];

    /// <summary>Anything unrecognised reads as <see cref="Best"/>, matching the column default.</summary>
    public static string Normalize(string? value)
    {
        var text = (value ?? string.Empty).Trim().ToLowerInvariant();
        return text == Ffmpeg ? Ffmpeg : Best;
    }

    /// <summary>True when the choice allows a writer other than ffmpeg to be preferred.</summary>
    public static bool PrefersBestTool(string? value) => Normalize(value) == Best;
}
