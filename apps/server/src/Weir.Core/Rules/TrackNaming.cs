using System.Text.RegularExpressions;

namespace Weir.Core.Rules;

/// <summary>
/// A track-name template used a placeholder that is not one of the supported names. Thrown by
/// <see cref="TrackNaming.ValidateTemplate"/> so a future settings API can point at the exact bad placeholder
/// before saving a template.
/// </summary>
public sealed class TrackNameTemplateException : Exception
{
    public TrackNameTemplateException(string message)
        : base(message)
    {
    }
}

/// <summary>
/// Per-flag template overrides (#498). Checked in this order — forced, then hearing-impaired, then commentary,
/// then audio description — against a track's <see cref="TrackFlags"/>; the first override whose flag is set and
/// whose template is non-empty wins. An empty template means "no override for this flag": fall back to
/// <see cref="MetadataRules.TrackNameTemplate"/>.
/// </summary>
public sealed record TrackNameOverrides
{
    public string Forced { get; init; } = "{language} {flags}";
    public string HearingImpaired { get; init; } = "{language} {flags}";
    public string Commentary { get; init; } = "{language} {flags}";
    public string AudioDescription { get; init; } = "{language} {flags}";
}

/// <summary>What one track's name is rendered from.</summary>
public sealed record TrackNameContext
{
    /// <summary>The language display text, e.g. "English" (<see cref="RemuxDisplay.LangDisplayOrBlank"/>).</summary>
    public string Language { get; init; } = string.Empty;

    /// <summary>
    /// A regional or dub marker (VFQ, Latino, …), when the track carries one. Populated by
    /// <see cref="TrackNaming.ContextFor"/> from #496's <see cref="PlannedTrack.Variant"/>.
    /// </summary>
    public string? Variant { get; init; }

    public int Channels { get; init; }
    public string CodecName { get; init; } = string.Empty;
    public TrackFlags Flags { get; init; } = new();
}

/// <summary>
/// The track-name template engine (#498, muxarr-inspired): resolves which template applies to a track, renders
/// its placeholders and validates a template for a future settings API. All-off <see cref="MetadataRules"/> means
/// this is never reached in ordinary remux planning, so it changes nothing for an upgrade.
/// </summary>
public static partial class TrackNaming
{
    /// <summary>
    /// <see cref="MetadataRules.TrackNameTemplate"/>'s default. <c>{variant}</c> renders as "" (nothing, not even
    /// a space) when the track has none, so the plain case reads e.g. "English 5.1 TrueHD" with no gap; when a
    /// variant is present it reads "English (VFQ) 5.1 TrueHD".
    /// </summary>
    public const string DefaultTemplate = "{language}{variant} {channels} {codec}";

    private static readonly string[] KnownPlaceholders = ["language", "variant", "channels", "codec", "flags"];

    [GeneratedRegex(@"\{(\w*)\}")]
    private static partial Regex PlaceholderRegex();

    [GeneratedRegex(@"\s+")]
    private static partial Regex WhitespaceRegex();

    /// <summary>
    /// Throws <see cref="TrackNameTemplateException"/> naming the first placeholder that is not one of
    /// <c>{language}</c>, <c>{variant}</c>, <c>{channels}</c>, <c>{codec}</c> or <c>{flags}</c>. A template with no
    /// placeholders at all, or only known ones, passes silently.
    /// </summary>
    public static void ValidateTemplate(string? template)
    {
        foreach (Match match in PlaceholderRegex().Matches(template ?? string.Empty))
        {
            var name = match.Groups[1].Value;
            if (!KnownPlaceholders.Contains(name, StringComparer.Ordinal))
            {
                throw new TrackNameTemplateException(
                    $"Unknown placeholder '{{{name}}}' in track name template. Supported placeholders: "
                    + string.Join(", ", KnownPlaceholders.Select(p => $"{{{p}}}")) + ".");
            }
        }
    }

    /// <summary>Validates <see cref="MetadataRules.TrackNameTemplate"/> and every non-empty override in one call, for a settings save.</summary>
    public static void ValidateAll(MetadataRules rules)
    {
        ArgumentNullException.ThrowIfNull(rules);
        ValidateTemplate(rules.TrackNameTemplate);
        ValidateTemplate(rules.TrackNameOverrides.Forced);
        ValidateTemplate(rules.TrackNameOverrides.HearingImpaired);
        ValidateTemplate(rules.TrackNameOverrides.Commentary);
        ValidateTemplate(rules.TrackNameOverrides.AudioDescription);
    }

    /// <summary>
    /// The template to use for a track with <paramref name="flags"/>: the first matching, non-empty override in
    /// <see cref="MetadataRules.TrackNameOverrides"/> (forced, hearing-impaired, commentary, audio description, in
    /// that order), or <see cref="MetadataRules.TrackNameTemplate"/> when none match.
    /// </summary>
    public static string ResolveTemplate(MetadataRules rules, TrackFlags flags)
    {
        ArgumentNullException.ThrowIfNull(rules);
        ArgumentNullException.ThrowIfNull(flags);
        var overrides = rules.TrackNameOverrides;
        if (flags.Forced.Value && overrides.Forced.Length > 0)
        {
            return overrides.Forced;
        }

        if (flags.HearingImpaired.Value && overrides.HearingImpaired.Length > 0)
        {
            return overrides.HearingImpaired;
        }

        if (flags.Commentary.Value && overrides.Commentary.Length > 0)
        {
            return overrides.Commentary;
        }

        if (flags.AudioDescription.Value && overrides.AudioDescription.Length > 0)
        {
            return overrides.AudioDescription;
        }

        return rules.TrackNameTemplate;
    }

    /// <summary>
    /// Renders <paramref name="template"/> against <paramref name="context"/>, then collapses runs of whitespace
    /// (left by an empty <c>{variant}</c> or <c>{flags}</c>) into single spaces and trims the ends. Validates
    /// first, so an unknown placeholder always throws rather than being left literal in the name.
    /// </summary>
    public static string Render(string template, TrackNameContext context)
    {
        ArgumentNullException.ThrowIfNull(template);
        ArgumentNullException.ThrowIfNull(context);
        ValidateTemplate(template);
        var flagsText = FormatFlags(context.Flags);
        var rendered = PlaceholderRegex().Replace(template, match => match.Groups[1].Value switch
        {
            "language" => context.Language,
            "variant" => string.IsNullOrEmpty(context.Variant) ? string.Empty : $" ({context.Variant})",
            "channels" => RemuxDisplay.ChannelsDisplay(context.Channels),
            "codec" => RemuxDisplay.CodecDisplayName(context.CodecName),
            "flags" => flagsText,
            _ => match.Value,
        });
        return WhitespaceRegex().Replace(rendered, " ").Trim();
    }

    /// <summary>Builds the naming context for a planned audio or subtitle track from what a <see cref="PlannedTrack"/> carries today.</summary>
    public static TrackNameContext ContextFor(PlannedTrack track)
    {
        ArgumentNullException.ThrowIfNull(track);
        return new TrackNameContext
        {
            Language = RemuxDisplay.LangDisplayOrBlank(track.LangLabel),
            Variant = track.Variant,
            Channels = track.Channels,
            CodecName = track.CodecName,
            Flags = new TrackFlags
            {
                Forced = track.Forced ? new TrackFlag(true, TrackFlagSource.Disposition) : TrackFlag.Absent,
                Commentary = track.Commentary ? new TrackFlag(true, TrackFlagSource.Disposition) : TrackFlag.Absent,

                // PlannedTrack does not carry these dispositions yet. Wire them from #495's TrackFlagsReader
                // (ffprobe's "hearing_impaired" and "visual_impaired" disposition flags) once the planner keeps
                // a track's full TrackFlags rather than only its Forced/Commentary booleans.
                HearingImpaired = TrackFlag.Absent,
                AudioDescription = TrackFlag.Absent,
            },
        };
    }

    /// <summary>The rendered title for one planned audio or subtitle track, using <see cref="MetadataRules.TrackNameTemplate"/> or the matching override.</summary>
    public static string RenderTrackName(MetadataRules rules, PlannedTrack track)
    {
        ArgumentNullException.ThrowIfNull(rules);
        var context = ContextFor(track);
        return Render(ResolveTemplate(rules, context.Flags), context);
    }

    private static string FormatFlags(TrackFlags flags)
    {
        var parts = new List<string>();
        if (flags.Forced.Value)
        {
            parts.Add("Forced");
        }

        if (flags.HearingImpaired.Value)
        {
            parts.Add("Hearing Impaired");
        }

        if (flags.Commentary.Value)
        {
            parts.Add("Commentary");
        }

        if (flags.AudioDescription.Value)
        {
            parts.Add("Audio Description");
        }

        return string.Join(", ", parts);
    }
}
