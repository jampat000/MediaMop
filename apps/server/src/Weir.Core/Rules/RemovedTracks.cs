namespace Weir.Core.Rules;

/// <summary>Which family of stream a removed track record describes (#509).</summary>
public enum RemovedTrackType
{
    Audio,
    Subtitle,
}

/// <summary>
/// One track a Processing pass removed from a file for good (issue #509, "getting a removed track back means
/// downloading again"). Populated by <see cref="RemuxRules.PlanRemux"/> from the same source data its
/// existing <see cref="RemuxPlan.RemovedAudio"/>/<see cref="RemuxPlan.RemovedSubtitles"/> display strings
/// are built from, so it needs no fragile parsing of those sentences.
///
/// <para><see cref="Variant"/> is the same regional/script variant identifier <c>LanguageVariants.Detect</c>
/// (issue #496) reads from the track's name or an explicit BCP 47 tag — e.g. "fre-CA" kept distinct from
/// plain "fre" — or null when the track carries no variant. #509's own base predated #496, so this used to
/// be always null; it is now filled from the same <c>AudioCandidate</c>/subtitle variant every other rule
/// here already computes, so "started keeping Japanese audio (Kansai dub)" can be judged at the variant
/// level, not only the base-language level.</para>
/// </summary>
public sealed record RemovedTrackRecord
{
    /// <summary>Normalized base language (<see cref="RemuxRules.NormalizeLang"/>), or "und" when the track named none.</summary>
    public required string Language { get; init; }

    public required RemovedTrackType Type { get; init; }

    /// <summary>ffprobe's <c>codec_name</c> (<see cref="Rules.ProbeStreamInfo.CodecName"/>), or "unknown" when it could not be read.</summary>
    public string Codec { get; init; } = "unknown";

    /// <summary>The track's regional/script variant identifier (issue #496), or null; see the type's remarks.</summary>
    public string? Variant { get; init; }

    /// <summary>Why it was removed, for an operator or the affected-titles list ("not selected — eng DTS 5.1 kept").</summary>
    public string Reason { get; init; } = string.Empty;
}
