using Weir.Core.Json;

namespace Weir.Core.Activity;

/// <summary>Stable <c>event_type</c> strings (port of <c>weir.platform.activity.constants</c>, auth part).</summary>
public static class ActivityEventTypes
{
    public const string AuthLoginSucceeded = "auth.login_succeeded";
    public const string AuthLoginFailed = "auth.login_failed";
    public const string AuthLogout = "auth.logout";
    public const string AuthBootstrapSucceeded = "auth.bootstrap_succeeded";
    public const string AuthBootstrapDenied = "auth.bootstrap_denied";
    public const string AuthPasswordChanged = "auth.password_changed";
    public const string AuthUsernameChanged = "auth.username_changed";
    public const string AuthSessionsRevoked = "auth.sessions_revoked";
}

/// <summary>The queryable facts lifted from an activity event when it is written.</summary>
public sealed record ActivityFacts(string? Trigger, string? Result, long? LibraryId, string? RelativePath, string? RunKey);

/// <summary>Port of <c>weir.platform.activity.classify.classify_activity</c>.</summary>
public static class ActivityClassifier
{
    private static readonly HashSet<string> Triggers = new(StringComparer.Ordinal)
    {
        "manual", "scheduled", "startup", "worker", "retry", "system", "webhook", "folder_change",
    };

    private static readonly HashSet<string> Results = new(StringComparer.Ordinal)
    {
        "success", "skipped", "warning", "retrying", "running", "failed",
    };

    private static readonly string[] PersonStartedPrefixes = ["auth.", "system.reconciliation."];

    private static readonly (string Word, string Result)[] ResultByTypeWord =
    [
        ("failed", "failed"), ("failure", "failed"), ("denied", "failed"), ("fell_back", "warning"),
        ("skipped", "skipped"), ("progress", "running"), ("started", "running"), ("succeeded", "success"),
        ("completed", "success"), ("passed_through", "success"), ("rejected", "success"), ("reported", "success"),
        ("cancelled", "success"),
    ];

    public static ActivityFacts Classify(string eventType, string? detail)
    {
        var data = DetailDict(detail) ?? new PyDict();
        var type = eventType ?? string.Empty;

        string? trigger = data.Get("trigger") is PyStr t && Triggers.Contains(t.Value.Trim().ToLowerInvariant()) ? t.Value.Trim().ToLowerInvariant() : null;
        if (trigger is null && PersonStartedPrefixes.Any(prefix => type.StartsWith(prefix, StringComparison.Ordinal)))
        {
            trigger = "manual";
        }

        string? result = data.Get("result") is PyStr r && Results.Contains(r.Value.Trim().ToLowerInvariant()) ? r.Value.Trim().ToLowerInvariant() : null;
        if (result is null && data.Get("ok") is PyBool { Value: false })
        {
            result = "failed";
        }

        if (result is null)
        {
            var lowered = type.ToLowerInvariant();
            result = ResultByTypeWord.FirstOrDefault(pair => lowered.Contains(pair.Word, StringComparison.Ordinal)).Result;
        }

        long? libraryId = data.Get("library_id") is PyInt i && i.Value >= long.MinValue && i.Value <= long.MaxValue ? (long)i.Value : null;
        string? relativePath = data.Get("relative_media_path") is PyStr p && p.Value.Trim().Length > 0 ? Truncate(p.Value.Trim(), 2000) : null;
        var runId = data.Get("run_id");
        string? runKey = runId is PyStr or PyInt or PyBool &&PyConvert.Str(runId).Trim().Length > 0 ? Truncate("run:" + PyConvert.Str(runId), 128) : null;
        return new ActivityFacts(trigger, result, libraryId, relativePath, runKey);
    }

    private static PyDict? DetailDict(string? detail)
    {
        var text = (detail ?? string.Empty).Trim();
        if (!text.StartsWith('{'))
        {
            return null;
        }

        try
        {
            return PyJsonParser.Parse(text) as PyDict;
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }
    }

    private static string Truncate(string value, int codePoints) => Auth.SessionRules.Truncate(value, codePoints);
}
