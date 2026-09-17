using Weir.Core.Refiner;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>
/// "Why is this file held?" (port of <c>refiner_hold_diagnostic_api.py</c>): ask every media manager
/// linked to this file's library what it is doing with it, right now. Deliberately live rather than
/// cached — the question is only ever asked because the recorded state looks wrong or stale, and answering
/// it from the same record would be no answer at all.
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

    /// <summary>
    /// Ask every manager linked to <paramref name="library"/> what it is importing, and apply the same
    /// domain rules the watched-folder scan applies per file (port of <c>get_refiner_file_why_held</c>).
    /// <paramref name="connections"/> is the shared connection-resolution/HTTP service (<c>manager_binding.py</c>,
    /// already ported): this call never duplicates its HTTP or dialect logic.
    /// </summary>
    public static async Task<CandidateGateOutcome> EvaluateAsync(
        UnitOfWork uow, RefinerFileRecord file, RefinerLibraryRecord library, MediaManagerConnectionService connections, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(file);
        ArgumentNullException.ThrowIfNull(library);
        ArgumentNullException.ThrowIfNull(connections);
        var scope = RefinerMediaScopes.Normalize(library.MediaType);
        var connectionIds = await LibraryStore.ManagerConnectionIdsAsync(uow, library.Id).ConfigureAwait(false);
        // `connection_ids or None`: unlike the watched-folder scan (which must ask nobody when a library
        // links nothing), this diagnostic falls back to every connection covering the scope when the
        // library names none — matching Python's hold-diagnostic endpoint exactly.
        var signals = await connections.CollectQueueSignalsAsync(
            uow, scope, connectionIds.Count > 0 ? connectionIds : null, cancellationToken).ConfigureAwait(false);
        var report = ManagerQueueSignals.ReportForSignals(signals);
        var candidate = new FileAnchorCandidate(ReleaseTitleFromRelativePath(file.RelativePath));
        var rows = ManagerQueueSignals.AttributedQueueRows(signals, scope, candidatePath: file.RelativePath);
        return CandidateGate.Evaluate(scope, report, rows, candidate);
    }
}
