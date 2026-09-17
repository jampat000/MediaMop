using Weir.Core.Refiner;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>
/// "Why is this file held?" (port of <c>refiner_hold_diagnostic_api.py</c>). The real answer asks every
/// linked media manager's live queue; that needs the manager-port HTTP clients from #520, which are not in
/// this build. Until then, a library's linked connections are reported as consulted-but-silent, which is
/// the honest state (Weir cannot yet get an import check from them) rather than a guessed verdict.
/// </summary>
public static class HoldDiagnosticStore
{
    /// <summary><c>_release_title_from_relative_path</c>: the folder name, or the file stem at the root.</summary>
    public static string ReleaseTitleFromRelativePath(string relativePath)
    {
        var parts = relativePath.Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length >= 2)
        {
            return parts[^2];
        }

        if (parts.Length == 0)
        {
            return relativePath;
        }

        var stem = parts[^1];
        var dot = stem.LastIndexOf('.');
        return dot > 0 ? stem[..dot] : stem;
    }

    /// <summary>Labels of the connections linked to a library, for the "no signal yet" report.</summary>
    public static async Task<List<string>> ConnectionLabelsAsync(UnitOfWork uow, IReadOnlyList<long> connectionIds)
    {
        if (connectionIds.Count == 0)
        {
            return [];
        }

        var placeholders = string.Join(",", connectionIds.Select((_, i) => $"@id{i}"));
        var parameters = connectionIds.Select((id, i) => ($"@id{i}", (object?)id)).ToArray();
        var rows = await uow.QueryAsync(
            $"SELECT kind, name FROM media_manager_connections WHERE id IN ({placeholders}) ORDER BY id",
            reader => (Kind: reader.GetString(0), Name: reader.GetString(1)), parameters).ConfigureAwait(false);
        return [.. rows.Select(row => LabelForConnection(row.Kind, row.Name))];
    }

    /// <summary><c>label_for_connection</c>: "Deluno (Main)" — what a blocked-upstream reason names.</summary>
    public static string LabelForConnection(string kind, string name)
    {
        var product = kind.Trim().ToLowerInvariant() switch
        {
            "radarr" => "Radarr",
            "sonarr" => "Sonarr",
            "deluno" => "Deluno",
            "native" => "Media manager",
            _ => "Media manager",
        };
        var label = (name ?? string.Empty).Trim();
        if (label.Length == 0)
        {
            return product;
        }

        return string.Equals(label, product, StringComparison.OrdinalIgnoreCase) ? product : $"{product} ({label})";
    }

    public static async Task<CandidateGateOutcome> EvaluateAsync(UnitOfWork uow, RefinerFileRecord file, RefinerLibraryRecord library)
    {
        var connectionIds = await LibraryStore.ManagerConnectionIdsAsync(uow, library.Id).ConfigureAwait(false);
        var labels = await ConnectionLabelsAsync(uow, connectionIds).ConfigureAwait(false);
        var report = new QueueSignalReport(connectionIds.Count, 0, labels);
        var scope = RefinerMediaScopes.Normalize(library.MediaType);
        var candidate = new FileAnchorCandidate(ReleaseTitleFromRelativePath(file.RelativePath));
        return CandidateGate.Evaluate(scope, report, [], candidate);
    }
}
