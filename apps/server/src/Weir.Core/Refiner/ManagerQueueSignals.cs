using Weir.Core.Json;
using Weir.Core.MediaManagers;

namespace Weir.Core.Refiner;

/// <summary>How to read the entity out of one queue row for a given media scope (<c>QueueDialect</c>).</summary>
public sealed record QueueDialect(
    string Scope,
    IReadOnlyList<string> EntityKeys,
    IReadOnlyList<string> EntityTitleFields,
    IReadOnlyList<string> EntityIdFields,
    IReadOnlySet<string> ActiveStatuses)
{
    /// <summary>Shared across every scope: a queue row is "upstream active" in the same states whatever produced it.</summary>
    public static readonly IReadOnlySet<string> DefaultActiveStatuses = new HashSet<string>(StringComparer.Ordinal)
    {
        "downloading", "queued", "paused", "delay", "downloadpending", "downloadclientunavailable", "warning",
    };
}

/// <summary>
/// Media-manager queue row -&gt; <see cref="RefinerQueueRowView"/>, driven by a media-scope dialect (port of
/// <c>queue_adapter.py</c> and the path-matching parts of <c>queue_row_plumbing.py</c>). A queue row differs
/// by what kind of library it describes, not by which product sent it: a movie row nests its entity under
/// <c>movie</c> and identifies it with <c>movieId</c>; an episode row nests under <c>series</c> and uses
/// <c>seriesId</c>. Neutral keys (<c>media</c>/<c>entityId</c>) let a manager that is neither Radarr nor
/// Sonarr use either dialect without vendor-specific code.
/// </summary>
public static class QueueRowMapping
{
    /// <summary><c>MOVIE_QUEUE_DIALECT</c>.</summary>
    public static readonly QueueDialect MovieDialect = new(
        MediaManagerKinds.Movie,
        ["movie", "media", "item"],
        ["title", "originalTitle", "original_title"],
        ["movieId", "movie_id", "entityId", "entity_id"],
        QueueDialect.DefaultActiveStatuses);

    /// <summary><c>TV_QUEUE_DIALECT</c>.</summary>
    public static readonly QueueDialect TvDialect = new(
        MediaManagerKinds.Tv,
        ["series", "show", "media", "item"],
        ["title", "sortTitle", "sort_title"],
        ["seriesId", "series_id", "entityId", "entity_id"],
        QueueDialect.DefaultActiveStatuses);

    private static readonly Dictionary<string, QueueDialect> DialectsByScope = new(StringComparer.Ordinal)
    {
        ["movie"] = MovieDialect,
        ["movies"] = MovieDialect,
        ["tv"] = TvDialect,
        ["series"] = TvDialect,
    };

    /// <summary><c>queue_dialect_for_scope</c>: resolve a dialect from a media-scope string, accepting the common spellings.</summary>
    public static QueueDialect DialectForScope(string scope)
    {
        var key = PyStrings.Strip(scope ?? string.Empty).ToLowerInvariant();
        if (DialectsByScope.TryGetValue(key, out var dialect))
        {
            return dialect;
        }

        throw new ArgumentException($"Unknown media scope for queue dialect: '{scope}'", nameof(scope));
    }

    /// <summary><c>normalize_storage_path</c>: normalize paths for equality (case-insensitive, forward slashes).</summary>
    public static string NormalizeStoragePath(string path) =>
        PyStrings.Strip(path.Replace('\\', '/')).ToLowerInvariant();

    /// <summary><c>primary_queue_status</c>: first non-empty status-like string.</summary>
    public static string PrimaryQueueStatus(PyDict row)
    {
        foreach (var key in (string[])["status", "trackedDownloadStatus", "trackedDownloadState"])
        {
            if (PyValues.Text(row.Get(key)) is { } found)
            {
                return found.ToLowerInvariant();
            }
        }

        return string.Empty;
    }

    /// <summary><c>output_path</c>.</summary>
    public static string? OutputPath(PyDict row) => PyValues.FirstText(row, "outputPath", "output_path");

    /// <summary><c>path_matches_candidate</c>.</summary>
    public static bool PathMatchesCandidate(PyDict row, string? candidatePath)
    {
        if (candidatePath is null)
        {
            return false;
        }

        return OutputPath(row) is { } outputPath && NormalizeStoragePath(outputPath) == NormalizeStoragePath(candidatePath);
    }

    /// <summary><c>blocking_suppressed_for_import_wait</c>.</summary>
    public static bool BlockingSuppressedForImportWait(PyDict row)
    {
        foreach (var key in (string[])["blockingSuppressedForImportWait", "blocking_suppressed_for_import_wait", "weirBlockingSuppressedForImportWait"])
        {
            if (row.Get(key) is PyBool flag)
            {
                return flag.Value;
            }
        }

        return false;
    }

    private static (string? Title, int? Year) QueueTitleAndYear(PyDict row, QueueDialect dialect)
    {
        foreach (var key in dialect.EntityKeys)
        {
            if (row.Get(key) is not PyDict entity)
            {
                continue;
            }

            var title = PyValues.FirstText(entity, [.. dialect.EntityTitleFields]);
            if (title is not null)
            {
                var year = PyValues.FirstNumber(entity, "year");
                return (title, year is { } y ? (int)y : null);
            }
        }

        // Year only ever comes from the nested entity, matching the previous per-vendor behaviour: a
        // top-level year on the row is not trusted to describe the entity.
        return (PyValues.FirstText(row, "title", "name"), null);
    }

    private static bool AppliesToFile(PyDict row, QueueDialect dialect, string? candidatePath, long? candidateEntityId)
    {
        if (PathMatchesCandidate(row, candidatePath))
        {
            return true;
        }

        if (candidateEntityId is null)
        {
            return false;
        }

        var rowId = PyValues.FirstNumber(row, [.. dialect.EntityIdFields]);
        return rowId is not null && (long)rowId == candidateEntityId;
    }

    /// <summary>
    /// <c>map_queue_row_to_refiner_view</c>: one media-manager queue row to the Refiner domain row view.
    /// <c>applies_to_file</c> is <c>outputPath</c> matching <paramref name="candidatePath"/>, and/or the row's
    /// scope id field matching <paramref name="candidateEntityId"/>; <c>queue_title</c>/<c>queue_year</c> come
    /// from the nested entity named by the dialect when present, else the row's top-level <c>title</c>/<c>name</c>.
    /// </summary>
    public static RefinerQueueRowView MapQueueRowToRefinerView(
        PyDict row, QueueDialect dialect, string? candidatePath = null, long? candidateEntityId = null)
    {
        ArgumentNullException.ThrowIfNull(row);
        ArgumentNullException.ThrowIfNull(dialect);
        var status = PrimaryQueueStatus(row);
        var isImportPending = status == "importpending";
        var isUpstreamActive = dialect.ActiveStatuses.Contains(status) && !isImportPending;
        var (title, year) = QueueTitleAndYear(row, dialect);
        return new RefinerQueueRowView(
            AppliesToFile: AppliesToFile(row, dialect, candidatePath, candidateEntityId),
            IsUpstreamActive: isUpstreamActive,
            IsImportPending: isImportPending,
            BlockingSuppressedForImportWait: BlockingSuppressedForImportWait(row),
            QueueTitle: title,
            QueueYear: year);
    }
}

/// <summary>One mapped queue row, plus the connection that reported it (<c>AttributedQueueRow</c>).</summary>
public sealed record AttributedQueueRow(string ConnectionLabel, RefinerQueueRowView View);

/// <summary>
/// Turn media-manager queue signals into Refiner domain rows that remember who said what (port of
/// <c>manager_queue_signals.py</c>). <see cref="RefinerDomain"/> decides whether a row blocks a file; it has
/// no idea which manager the row came from, and should not — attribution is carried alongside the view here,
/// which is what lets a blocked-upstream reason say "Deluno (Main) is still importing this file" instead of
/// naming a product the operator may not even have installed.
/// </summary>
public static class ManagerQueueSignals
{
    /// <summary>
    /// <c>attributed_queue_rows</c>: map every reported row for <paramref name="mediaScope"/> through its
    /// dialect, keeping the reporter's name. Rows describing the other kind of library are dropped rather
    /// than mapped: a manager that serves both scopes reports on its whole instance, and an in-flight TV
    /// import carries a title and year that the anchor rules will match against a film with a similar name.
    /// </summary>
    public static List<AttributedQueueRow> AttributedQueueRows(
        IReadOnlyList<ManagerQueueSignal> signals, string mediaScope, string? candidatePath = null, long? candidateEntityId = null)
    {
        ArgumentNullException.ThrowIfNull(signals);
        var rows = new List<AttributedQueueRow>();
        var dialect = QueueRowMapping.DialectForScope(mediaScope);
        foreach (var signal in signals)
        {
            if (!signal.IsReported)
            {
                continue;
            }

            var label = signal.Connection.Label;
            foreach (var row in signal.Rows)
            {
                if (row.Scope != mediaScope)
                {
                    continue;
                }

                rows.Add(new AttributedQueueRow(label, QueueRowMapping.MapQueueRowToRefinerView(row.Payload, dialect, candidatePath, candidateEntityId)));
            }
        }

        return rows;
    }

    /// <summary>
    /// <c>attributed_rows_for_file</c>: the rows any manager holds against one file on disk, within its own
    /// scope. <paramref name="resolvedFilePath"/> must already be the fully resolved absolute path — resolving
    /// it is the caller's job, since it touches the filesystem and this module stays IO-free.
    /// </summary>
    public static List<AttributedQueueRow> AttributedRowsForFile(
        IReadOnlyList<ManagerQueueSignal> signals, string mediaScope, string resolvedFilePath) =>
        AttributedQueueRows(signals, mediaScope, candidatePath: resolvedFilePath);

    /// <summary><c>views_of</c>.</summary>
    public static List<RefinerQueueRowView> ViewsOf(IReadOnlyList<AttributedQueueRow> rows) =>
        [.. rows.Select(r => r.View)];

    /// <summary><c>file_is_owned_by_any_manager</c>.</summary>
    public static bool FileIsOwnedByAnyManager(IReadOnlyList<AttributedQueueRow> rows, FileAnchorCandidate? candidate = null) =>
        RefinerDomain.FileIsOwnedByQueue(ViewsOf(rows), candidate);

    /// <summary>
    /// <c>blocking_connection_label</c>: the first connection holding this file open, or <see langword="null"/>
    /// if none is. A block from any manager blocks the file, so the first one found is enough to explain the wait.
    /// </summary>
    public static string? BlockingConnectionLabel(IReadOnlyList<AttributedQueueRow> rows, FileAnchorCandidate? candidate = null)
    {
        ArgumentNullException.ThrowIfNull(rows);
        foreach (var row in rows)
        {
            if (RefinerDomain.ShouldBlockForUpstream([row.View], candidate))
            {
                return row.ConnectionLabel;
            }
        }

        return null;
    }

    /// <summary><c>upstream_block_reason</c>: plain-language reason naming the connection, not the vendor.</summary>
    public static string? UpstreamBlockReason(IReadOnlyList<AttributedQueueRow> rows, FileAnchorCandidate? candidate = null)
    {
        var label = BlockingConnectionLabel(rows, candidate);
        return label is null ? null : $"{label} is still importing this file, so Weir left it alone for now.";
    }

    /// <summary><c>report_for_signals</c>.</summary>
    public static QueueSignalReport ReportForSignals(IReadOnlyList<ManagerQueueSignal> signals)
    {
        ArgumentNullException.ThrowIfNull(signals);
        var silentLabels = new List<string>();
        var silentDetails = new List<string>();
        var reported = 0;
        foreach (var signal in signals)
        {
            if (signal.IsReported)
            {
                reported++;
                continue;
            }

            silentLabels.Add(signal.Connection.Label);
            silentDetails.Add(string.IsNullOrEmpty(signal.Detail) ? $"{signal.Connection.Label} did not answer." : signal.Detail);
        }

        return new QueueSignalReport(signals.Count, reported, silentLabels, silentDetails);
    }
}
