using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>One filesystem/database finding (<c>ReconciliationIssue</c>).</summary>
public sealed record ReconciliationIssue(
    string Kind,
    string Module,
    string Severity,
    string Message,
    string? Path = null,
    string? DbTable = null,
    long? DbId = null,
    string? RepairAction = null,
    bool RequiresConfirmation = false)
{
    public PyDict AsDict() => new PyDict()
        .Set("kind", Kind)
        .Set("module", Module)
        .Set("severity", Severity)
        .Set("message", Message)
        .Set("path", Path)
        .Set("db_table", DbTable)
        .Set("db_id", DbId)
        .Set("repair_action", RepairAction)
        .Set("requires_confirmation", RequiresConfirmation);
}

/// <summary>The pure parts of <c>weir.platform.reconciliation.service</c>.</summary>
public static class ReconciliationRules
{
    public const string RemoveTempArtifactAction = "remove_refiner_temp_artifact";
    public const int MaxIssuesPerCategory = 200;

    /// <summary><c>TEMP_ARTIFACT_SUFFIXES</c>.</summary>
    public static readonly IReadOnlyList<string> TempArtifactSuffixes = [".partial", ".part", ".tmp", ".link"];

    /// <summary><c>_is_temp_artifact</c> on a file name.</summary>
    public static bool IsTempArtifactName(string name)
    {
        ArgumentNullException.ThrowIfNull(name);
        var lower = name.ToLowerInvariant();
        return lower.StartsWith('.') || TempArtifactSuffixes.Any(suffix => lower.EndsWith(suffix, StringComparison.Ordinal));
    }

    /// <summary><c>build_reconciliation_report</c>'s shape.</summary>
    public static PyDict Report(IReadOnlyList<ReconciliationIssue> issues)
    {
        ArgumentNullException.ThrowIfNull(issues);
        return new PyDict()
            .Set("ok", issues.Count == 0)
            .Set("issue_count", issues.Count)
            .Set("issues", new PyList(issues.Select(issue => (PyJson)issue.AsDict())))
            .Set("repair_actions", new PyList(issues
                .Select(issue => issue.RepairAction)
                .Where(action => !string.IsNullOrEmpty(action))
                .Distinct(StringComparer.Ordinal)
                .Order(StringComparer.Ordinal)
                .Select(action => (PyJson)new PyStr(action!))));
    }
}
