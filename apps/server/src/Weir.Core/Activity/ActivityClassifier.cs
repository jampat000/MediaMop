using Weir.Core.Json;

namespace Weir.Core.Activity;

/// <summary>
/// The queryable facts about an activity event, lifted into columns when it is written
/// (port of <c>weir.platform.activity.classify.ActivityFacts</c>, #469).
/// </summary>
public sealed record ActivityFacts(string? Trigger, string? Result, long? LibraryId, string? RelativePath, string? RunKey);

/// <summary>Port of <c>weir.platform.activity.classify.classify_activity</c>.</summary>
/// <remarks>
/// The detail is read with <see cref="PyJsonParser"/>, so it parses exactly what <c>json.loads</c> parses
/// (<c>NaN</c>, integers of any size, the last duplicate key winning), and text is trimmed with
/// Python's <c>str.strip()</c>.
/// </remarks>
public static class ActivityClassifier
{
    /// <summary><c>TRIGGERS</c>: <c>docs/operator-messaging-standard.md</c>, plus <c>webhook</c> and <c>folder_change</c>.</summary>
    public static readonly IReadOnlySet<string> Triggers = new HashSet<string>(StringComparer.Ordinal)
    {
        "manual", "scheduled", "startup", "worker", "retry", "system", "webhook", "folder_change",
    };

    /// <summary><c>RESULTS</c>.</summary>
    public static readonly IReadOnlySet<string> Results = new HashSet<string>(StringComparer.Ordinal)
    {
        "success", "skipped", "warning", "retrying", "running", "failed",
    };

    private static readonly string[] PersonStartedPrefixes = ["auth.", "system.reconciliation."];

    // Read from the event type only when the producer did not say. Ordered: the first match wins,
    // so "fell_back" is a warning even though the event also completed.
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
        var data = DetailDict(detail) ?? new PyDict();
        var type = eventType ?? string.Empty;

        var trigger = Member(data.Get("trigger"), Triggers);
        if (trigger is null && PersonStartedPrefixes.Any(prefix => type.StartsWith(prefix, StringComparison.Ordinal)))
        {
            // A sign-in, a password change or a repair someone clicked is, by definition, someone's action.
            trigger = "manual";
        }

        var result = Member(data.Get("result"), Results);
        if (result is null && data.Get("ok") is PyBool { Value: false })
        {
            result = "failed";
        }

        if (result is null)
        {
            var lowered = type.ToLowerInvariant();
            // #540 item 8: Python scans for the first word that occurs anywhere in the event type, so
            // "refiner.failure_cleanup_sweep_completed" reads as "failed" because "failure" is checked
            // before "completed" ever gets a look in, even though "completed" is the type's actual
            // terminal verb. An event type's own name always ends in its terminal verb, so a suffix
            // match is checked first and wins; only when nothing is a suffix does the old substring
            // scan run, matching Python for the handful of odd names that will not benefit.
            result = ResultByTypeWord.FirstOrDefault(pair => lowered.EndsWith(pair.Word, StringComparison.Ordinal)).Result
                ?? ResultByTypeWord.FirstOrDefault(pair => lowered.Contains(pair.Word, StringComparison.Ordinal)).Result;
        }

        // isinstance(x, int) and not isinstance(x, bool); a value beyond SQLite's INTEGER is left out.
        long? libraryId = data.Get("library_id") is PyInt i && i.Value >= long.MinValue && i.Value <= long.MaxValue ? (long)i.Value : null;

        string? relativePath = null;
        if (data.Get("relative_media_path") is PyStr path && PyStrings.Strip(path.Value) is { Length: > 0 } stripped)
        {
            relativePath = PyStrings.Slice(stripped, 2000);
        }

        // #540 item 5: strict payload parsing. Python's isinstance(run_id, (str, int)) also accepts a
        // bool (a bool is an int in Python), so run_id: true became the literal run key "run:True".
        // Booleans are rejected here instead, the same as library_id below.
        string? runKey = null;
        if (data.Get("run_id") is (PyStr or PyInt) and var runId && PyStrings.Strip(PyConvert.Str(runId)).Length > 0)
        {
            runKey = PyStrings.Slice("run:" + PyConvert.Str(runId), 128);
        }

        return new ActivityFacts(trigger, result, libraryId, relativePath, runKey);
    }

    private static string? Member(PyJson? value, IReadOnlySet<string> allowed)
    {
        if (value is not PyStr text)
        {
            return null;
        }

        var normalized = PyStrings.Strip(text.Value).ToLowerInvariant();
        return allowed.Contains(normalized) ? normalized : null;
    }

    /// <summary><c>_detail_dict</c>.</summary>
    private static PyDict? DetailDict(string? detail)
    {
        var text = PyStrings.Strip(detail ?? string.Empty);
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
}
