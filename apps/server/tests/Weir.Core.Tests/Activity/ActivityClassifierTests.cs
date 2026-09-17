using System.Reflection;
using System.Text.RegularExpressions;
using Weir.Core.Activity;

namespace Weir.Core.Tests.Activity;

/// <summary>
/// Ports of <c>classify_activity</c>'s behaviour and the <c>constants</c> contract. Expected facts were
/// produced by the Python function.
/// </summary>
public sealed partial class ActivityClassifierTests
{
    [Fact]
    public void Facts_are_lifted_from_the_detail()
    {
        Assert.Equal(
            new ActivityFacts("worker", "warning", 3, "Movies/a.mkv", "run:7"),
            ActivityClassifier.Classify("refiner.file_processed", "{\"trigger\": \" Worker \", \"result\": \"warning\", \"library_id\": 3, \"relative_media_path\": \" Movies/a.mkv \", \"run_id\": 7}"));
        Assert.Equal(
            new ActivityFacts("scheduled", "retrying", 4, "a/b.mkv", "run:9"),
            ActivityClassifier.Classify(
                ActivityEventTypes.RefinerWorkerFailure,
                "{\"job_id\":3,\"result\":\"Retrying\",\"trigger\":\" Scheduled \",\"library_id\":4,\"relative_media_path\":\" a/b.mkv \",\"run_id\":9}"));
        Assert.Equal("skipped", ActivityClassifier.Classify(ActivityEventTypes.RefinerFailureCleanupSweepCompleted, "{\"result\":\"skipped\"}").Result);
    }

    [Fact]
    public void Person_started_events_are_manual_and_results_fall_back_to_the_event_type()
    {
        Assert.Equal(new ActivityFacts("manual", "success", null, null, null), ActivityClassifier.Classify(ActivityEventTypes.AuthLoginSucceeded, "alice"));
        Assert.Equal(new ActivityFacts("manual", "failed", null, null, null), ActivityClassifier.Classify(ActivityEventTypes.AuthBootstrapDenied, "An admin account already exists."));
        Assert.Equal(new ActivityFacts("manual", null, null, null, null), ActivityClassifier.Classify(ActivityEventTypes.SystemReconciliationRepair, null));
        Assert.Equal(new ActivityFacts(null, "failed", null, null, null), ActivityClassifier.Classify(ActivityEventTypes.RefinerWorkerFailure, null));
        // #540 item 8: Python checks "failure" (in the event type's name) before "completed", so a
        // cleanup sweep that finished with no result given reads as "failed". Fixed here to match the
        // type's own terminal verb ("completed") first, so it reads as "success" instead.
        Assert.Equal("success", ActivityClassifier.Classify(ActivityEventTypes.RefinerFailureCleanupSweepCompleted, "not json").Result);
        Assert.Equal("warning", ActivityClassifier.Classify(ActivityEventTypes.RefinerFileRejectFellBack, null).Result);
    }

    [Fact]
    public void Booleans_are_not_library_ids_and_not_run_ids()
    {
        Assert.Equal(new ActivityFacts(null, "failed", null, null, null), ActivityClassifier.Classify("refiner.x", "{\"ok\": false, \"library_id\": true}"));
        // #540 item 5: Python's isinstance(run_id, (str, int)) also accepts a bool, so run_id: true
        // read as the run key "run:True". Fixed here to reject booleans, so neither id is set.
        Assert.Equal(new ActivityFacts("manual", "failed", null, null, null), ActivityClassifier.Classify("auth.login", "{\"ok\":false,\"library_id\":true,\"run_id\":true}"));
        Assert.Equal(new ActivityFacts(null, null, null, null, null), ActivityClassifier.Classify("refiner.x", "{\"library_id\": 1.0, \"run_id\": \" \"}"));
    }

    [Fact]
    public void The_detail_is_read_the_way_json_loads_and_str_strip_read_it()
    {
        // json.loads accepts NaN, keeps integers of any size and lets the last duplicate key win.
        Assert.Equal("worker", ActivityClassifier.Classify("refiner.x", "{\"trigger\":\"worker\",\"x\":NaN}").Trigger);
        Assert.Equal("retry", ActivityClassifier.Classify("refiner.x", "{\"trigger\":\"worker\",\"trigger\":\"retry\"}").Trigger);
        Assert.Equal(
            "run:123456789012345678901234567890",
            ActivityClassifier.Classify("refiner.x", "{\"run_id\":123456789012345678901234567890}").RunKey);
        // str.strip() removes U+001C..U+001F, which .NET's Trim keeps.
        Assert.Equal(
            new ActivityFacts("worker", null, null, "a", null),
            ActivityClassifier.Classify("refiner.x", "{\"trigger\":\"\\u001cWorker\\u001c\",\"relative_media_path\":\"\\u2028a\\u001f\"}"));
        Assert.Equal(2000, ActivityClassifier.Classify("refiner.x", "{\"relative_media_path\":\"" + new string('p', 2500) + "\"}").RelativePath!.Length);
    }

    [Fact]
    public void Event_types_match_the_python_constants_exactly()
    {
        var constants = FindBackendFile("apps", "backend", "src", "weir", "platform", "activity", "constants.py");
        var python = PythonConstant().Matches(File.ReadAllText(constants))
            .ToDictionary(match => match.Groups[1].Value.Replace("_", string.Empty, StringComparison.Ordinal).ToUpperInvariant(), match => match.Groups[2].Value);
        var dotnet = typeof(ActivityEventTypes).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(field => !CSharpOnlyEventTypes.Contains(field.Name))
            .ToDictionary(field => field.Name.ToUpperInvariant(), field => (string)field.GetValue(null)!);

        Assert.NotEmpty(python);
        Assert.Equal(python.OrderBy(pair => pair.Key, StringComparer.Ordinal), dotnet.OrderBy(pair => pair.Key, StringComparer.Ordinal));
        foreach (var name in CSharpOnlyEventTypes)
        {
            Assert.NotNull(typeof(ActivityEventTypes).GetField(name, BindingFlags.Public | BindingFlags.Static));
        }
    }

    /// <summary>
    /// Event types for features added after ADR-0017 froze the switch-over plan, with no Python equivalent — Python
    /// is retiring (#523) and is not touched to add a constant for a C#-only feature.
    /// </summary>
    private static readonly HashSet<string> CSharpOnlyEventTypes = new(StringComparer.Ordinal)
    {
        // Issue #501: choosing tracks by hand for a held file. The manual-plan endpoints and the remux pass's
        // handling of them exist only in the .NET server.
        nameof(ActivityEventTypes.RefinerFileManualPlanQueued),
    };

    private static string FindBackendFile(params string[] parts)
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        {
            var candidate = Path.Join([directory.FullName, .. parts]);
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        throw new FileNotFoundException("The Python backend source was not found above the test assembly.", Path.Join(parts));
    }

    [GeneratedRegex("^([A-Z][A-Z0-9_]*) = \"([^\"]*)\"", RegexOptions.Multiline)]
    private static partial Regex PythonConstant();
}
