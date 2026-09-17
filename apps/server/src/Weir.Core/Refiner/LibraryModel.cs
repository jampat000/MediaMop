using Weir.Core.Time;

namespace Weir.Core.Refiner;

/// <summary>The two Refiner media scopes (<c>REFINER_MEDIA_SCOPES</c>).</summary>
public static class RefinerMediaScopes
{
    public const string Movie = "movie";
    public const string Tv = "tv";

    public static readonly IReadOnlyList<string> All = [Movie, Tv];

    /// <summary><c>normalize_media_scope</c>.</summary>
    public static string Normalize(string? raw) => string.Equals((raw ?? Movie).Trim(), Tv, StringComparison.OrdinalIgnoreCase) ? Tv : Movie;
}

/// <summary>The three Refiner failure policies (<c>refiner_pass_through.FAILURE_POLICIES</c>).</summary>
public static class RefinerFailurePolicies
{
    public const string PassThrough = "pass_through";
    public const string Hold = "hold";
    public const string Reject = "reject";

    public static readonly IReadOnlyList<string> All = [PassThrough, Hold, Reject];

    /// <summary><c>normalize_failure_policy</c>: anything unrecognised is the product's guarantee, pass_through.</summary>
    public static string Normalize(string? raw)
    {
        var value = (raw ?? string.Empty).Trim().ToLowerInvariant();
        return All.Contains(value, StringComparer.Ordinal) ? value : PassThrough;
    }
}

/// <summary>One <c>refiner_rule_sets</c> row.</summary>
public sealed record RefinerRuleSetRecord
{
    public long Id { get; init; }
    public required string Name { get; init; }
    public string PrimaryAudioLang { get; init; } = string.Empty;
    public string SecondaryAudioLang { get; init; } = string.Empty;
    public string TertiaryAudioLang { get; init; } = string.Empty;
    public string DefaultAudioSlot { get; init; } = "primary";
    public bool RemoveCommentary { get; init; }
    public string SubtitleMode { get; init; } = "keep_all";
    public string SubtitleLangsCsv { get; init; } = string.Empty;
    public bool PreserveForcedSubs { get; init; } = true;
    public bool PreserveDefaultSubs { get; init; } = true;
    public string AudioPreferenceMode { get; init; } = "preferred_langs_quality";
    public string AudioSortersJson { get; init; } = string.Empty;
    public string SubtitleSortersJson { get; init; } = string.Empty;
    public bool KeepOriginalLanguage { get; init; }
    public string OriginalLanguageAdditionalCsv { get; init; } = string.Empty;
    public bool OriginalLanguageKeepOnlyFirst { get; init; } = true;
    public bool OriginalLanguageFirstIfNone { get; init; } = true;
    public bool OriginalLanguageTreatEmptyAsOriginal { get; init; }
    public bool RemoveImages { get; init; }
    public bool RemoveAttachments { get; init; }
    public bool RemoveTitle { get; init; }
    public bool RemoveLanguageTags { get; init; }
    public bool RemoveOtherMetadata { get; init; }
    public PyDateTime CreatedAt { get; init; }
    public PyDateTime UpdatedAt { get; init; }
}

/// <summary>One <c>refiner_libraries</c> row.</summary>
public sealed record RefinerLibraryRecord
{
    public long Id { get; init; }
    public required string Name { get; init; }
    public bool Enabled { get; init; } = true;
    public string MediaType { get; init; } = RefinerMediaScopes.Movie;
    public long DisplayOrder { get; init; }

    public string WatchedFolder { get; init; } = string.Empty;
    public string WorkFolder { get; init; } = string.Empty;
    public string OutputFolder { get; init; } = string.Empty;

    public string MediaExtensionsCsv { get; init; } = string.Empty;
    public string ExcludeMarkersCsv { get; init; } = string.Empty;
    public string IncludePatternsCsv { get; init; } = string.Empty;
    public string ExcludePatternsCsv { get; init; } = string.Empty;
    public long MinFileSizeMb { get; init; }
    public long MaxFileSizeMb { get; init; }
    public string RejectedFileAction { get; init; } = "leave";
    public long MinFileAgeSeconds { get; init; } = 60;
    public PyDateTime? CreatedAfter { get; init; }
    public PyDateTime? CreatedBefore { get; init; }
    public PyDateTime? ModifiedAfter { get; init; }
    public PyDateTime? ModifiedBefore { get; init; }
    public bool ExcludeHidden { get; init; } = true;
    public bool TopLevelOnly { get; init; }

    public string SidecarPatternsCsv { get; init; } = ".srt,.ass,.ssa,.sub,.idx,.vtt,.nfo,.jpg,.png";
    public bool PreserveOriginalTimestamps { get; init; }
    public string OutputCollisionPolicy { get; init; } = "replace";

    public string HardwareDecodeMode { get; init; } = "off";
    public string HardwareDevice { get; init; } = string.Empty;
    public string HardwareDisabledVendorsCsv { get; init; } = string.Empty;
    public string FfmpegStrictness { get; init; } = "normal";

    public long ScanIntervalSeconds { get; init; } = 300;
    public long HoldMinutes { get; init; }
    public long FileDetectionIntervalSeconds { get; init; } = 30;
    public bool IgnoreSizeChanges { get; init; }
    public bool FileSystemEventsEnabled { get; init; } = true;
    public bool SkipAccessTests { get; init; }
    public bool ScheduleEnabled { get; init; } = true;
    public bool ScheduleHoursLimited { get; init; }
    public string ScheduleDays { get; init; } = string.Empty;
    public string ScheduleGrid { get; init; } = string.Empty;
    public string ScheduleStart { get; init; } = "00:00";
    public string ScheduleEnd { get; init; } = "23:59";

    public long MaxAttempts { get; init; } = 3;
    public long RetryBackoffSeconds { get; init; } = 300;
    public bool RetryExecutionFailures { get; init; } = true;
    public bool RetryPreflightFailures { get; init; }
    public string FailurePolicy { get; init; } = RefinerFailurePolicies.PassThrough;

    public long MaxConcurrentFiles { get; init; } = 1;
    public long Priority { get; init; }

    public long? RuleSetId { get; init; }
    public long? DiscoveredFromConnectionId { get; init; }
    public string? DiscoveredLibraryKey { get; init; }

    public PyDateTime CreatedAt { get; init; }
    public PyDateTime UpdatedAt { get; init; }
}
