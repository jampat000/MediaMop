using System.Globalization;
using System.Text.Json;
using Weir.Core.Jobs;

namespace Weir.Core.Activity;

/// <summary>
/// The queryable facts about an activity event, lifted into columns when it is written
/// (port of <c>weir.platform.activity.classify</c>, #469).
/// </summary>
public sealed record ActivityFacts(string? Trigger, string? Result, long? LibraryId, string? RelativePath, string? RunKey)
{
    public static readonly IReadOnlySet<string> Triggers =
        new HashSet<string>(StringComparer.Ordinal) { "manual", "scheduled", "startup", "worker", "retry", "system", "webhook", "folder_change" };

    public static readonly IReadOnlySet<string> Results =
        new HashSet<string>(StringComparer.Ordinal) { "success", "skipped", "warning", "retrying", "running", "failed" };

    private static readonly string[] PersonStartedPrefixes = ["auth.", "system.reconciliation."];

    private static readonly (string Word, string Result)[] ResultByTypeWord =
    [
        ("failed", "failed"),
        ("failure", "failed"),
        ("denied", "failed"),
        ("fell_back", "warning"),
        ("skipped", "skipped"),
        ("progress", "running"),
        ("started", "running"),
        ("succeeded", "success"),
        ("completed", "success"),
        ("passed_through", "success"),
        ("rejected", "success"),
        ("reported", "success"),
        ("cancelled", "success"),
    ];

    /// <summary><c>classify_activity</c>.</summary>
    public static ActivityFacts Classify(string eventType, string? detail)
    {
        ArgumentNullException.ThrowIfNull(eventType);
        var text = (detail ?? string.Empty).Trim();
        var data = text.StartsWith('{') ? JobPayload.ParseObject(text) : null;

        var trigger = LowerMember(JobPayload.StringProperty(data, "trigger"), Triggers);
        if (trigger is null && PersonStartedPrefixes.Any(prefix => eventType.StartsWith(prefix, StringComparison.Ordinal)))
        {
            trigger = "manual";
        }

        var result = LowerMember(JobPayload.StringProperty(data, "result"), Results);
        if (result is null && data is { } element && element.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.False)
        {
            result = "failed";
        }

        if (result is null)
        {
            var lowered = eventType.ToLowerInvariant();
            result = ResultByTypeWord.Where(pair => lowered.Contains(pair.Word, StringComparison.Ordinal)).Select(pair => pair.Result).FirstOrDefault();
        }

        var libraryId = JobPayload.StrictInteger(data, "library_id");

        var relative = JobPayload.StringProperty(data, "relative_media_path");
        relative = relative is not null && relative.Trim().Length > 0 ? OperatorFailures.PythonSlice(relative.Trim(), 2000) : null;

        string? runKey = null;
        if (data is { } payload && payload.TryGetProperty("run_id", out var runId))
        {
            var runText = runId.ValueKind switch
            {
                JsonValueKind.String => runId.GetString(),
                JsonValueKind.True => "True",
                JsonValueKind.False => "False",
                JsonValueKind.Number when JobPayload.StrictInteger(data, "run_id") is { } number => number.ToString(CultureInfo.InvariantCulture),
                _ => null,
            };
            if (runText is not null && runText.Trim().Length > 0)
            {
                runKey = OperatorFailures.PythonSlice($"run:{runText}", 128);
            }
        }

        return new ActivityFacts(trigger, result, libraryId, relative, runKey);
    }

    private static string? LowerMember(string? value, IReadOnlySet<string> allowed)
    {
        if (value is null)
        {
            return null;
        }

        var normalized = value.Trim().ToLowerInvariant();
        return allowed.Contains(normalized) ? normalized : null;
    }
}
