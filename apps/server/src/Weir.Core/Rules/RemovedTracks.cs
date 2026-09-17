namespace Weir.Core.Rules;

/// <summary>Which family of stream a removed track record describes (#509).</summary>
public enum RemovedTrackType
{
    Audio,
    Subtitle,
}

/// <summary>
/// One track a Refiner pass removed from a file for good (issue #509, "getting a removed track back means
/// downloading again"). Populated by <see cref="RemuxRules.PlanRemux"/> from the same source data its
/// existing <see cref="RemuxPlan.RemovedAudio"/>/<see cref="RemuxPlan.RemovedSubtitles"/> display strings
/// are built from, so it needs no fragile parsing of those sentences.
///
/// <para><see cref="Variant"/> is always null today: this codebase has no <c>LanguageVariants</c> concept
/// (a track carries one normalized language tag — <see cref="RemuxRules.NormalizeLang"/> — and nothing
/// distinguishes two tracks tagged with the same language). "Started keeping Japanese audio" can therefore
/// only be judged at the base-language level; <c>Weir.Core.Library.RemovedTrackDiff</c> documents that
/// limitation where it matters. If a future change adds a variant concept (region, dub vs. original, and
/// so on), this is the field to populate — the diff already treats a non-null variant as significant.</para>
/// </summary>
public sealed record RemovedTrackRecord
{
    /// <summary>Normalized base language (<see cref="RemuxRules.NormalizeLang"/>), or "und" when the track named none.</summary>
    public required string Language { get; init; }

    public required RemovedTrackType Type { get; init; }

    /// <summary>ffprobe's <c>codec_name</c> (<see cref="Rules.ProbeStreamInfo.CodecName"/>), or "unknown" when it could not be read.</summary>
    public string Codec { get; init; } = "unknown";

    /// <summary>Always null in this codebase today; see the type's remarks.</summary>
    public string? Variant { get; init; }

    /// <summary>Why it was removed, for an operator or the affected-titles list ("not selected — eng DTS 5.1 kept").</summary>
    public string Reason { get; init; } = string.Empty;
}
