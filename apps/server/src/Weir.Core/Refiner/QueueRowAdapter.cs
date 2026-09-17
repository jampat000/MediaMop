using Weir.Core.Json;
using Weir.Core.MediaManagers;

namespace Weir.Core.Refiner;

/// <summary>
/// Generic JSON/path helpers for a media manager's queue rows, with no per-product semantics (port of
/// <c>weir.refiner.queue_row_plumbing</c>).
/// </summary>
public static class QueueRowPlumbing
{
    /// <summary><c>normalize_storage_path</c>: case-insensitive, forward slashes.</summary>
    public static string NormalizeStoragePath(string path)
    {
        ArgumentNullException.ThrowIfNull(path);
        return PyStrings.Strip(path.Replace('\\', '/')).ToLowerInvariant();
    }

    /// <summary><c>output_path</c>.</summary>
    public static string? OutputPath(PyDict row) => PyValues.FirstText(row, "outputPath", "output_path");

    /// <summary><c>path_matches_candidate</c>: exact match once both sides are normalized.</summary>
    public static bool PathMatchesCandidate(PyDict row, string? candidatePath)
    {
        if (candidatePath is null || OutputPath(row) is not { } outputPath)
        {
            return false;
        }

        return NormalizeStoragePath(outputPath) == NormalizeStoragePath(candidatePath);
    }

    /// <summary><c>primary_queue_status</c>: the first non-empty status-like string, lower-cased.</summary>
    public static string PrimaryQueueStatus(PyDict row)
    {
        ArgumentNullException.ThrowIfNull(row);
        foreach (var key in new[] { "status", "trackedDownloadStatus", "trackedDownloadState" })
        {
            if (PyValues.Text(row.Get(key)) is { } value)
            {
                return value.ToLowerInvariant();
            }
        }

        return string.Empty;
    }

    /// <summary><c>blocking_suppressed_for_import_wait</c>.</summary>
    public static bool BlockingSuppressedForImportWait(PyDict row)
    {
        ArgumentNullException.ThrowIfNull(row);
        foreach (var key in new[] { "blockingSuppressedForImportWait", "blocking_suppressed_for_import_wait", "weirBlockingSuppressedForImportWait" })
        {
            if (row.Get(key) is PyBool boolean)
            {
                return boolean.Value;
            }
        }

        return false;
    }
}

/// <summary>How to read the entity out of one queue row for a given media scope (<c>QueueDialect</c>).</summary>
public sealed record QueueDialect(
    string Scope,
    IReadOnlyList<string> EntityKeys,
    IReadOnlyList<string> EntityTitleFields,
    IReadOnlyList<string> EntityIdFields,
    IReadOnlySet<string> ActiveStatuses);

/// <summary>
/// Media-manager queue row to <see cref="RefinerQueueRowView"/>, driven by a media-scope dialect (port of
/// <c>weir.refiner.queue_adapter</c>). A queue row differs by what kind of library it describes, not by which product
/// sent it: a movie row nests its entity under <c>movie</c> and identifies it with <c>movieId</c>; an episode row nests
/// under <c>series</c> and uses <c>seriesId</c>.
/// </summary>
public static class QueueRowAdapter
{
    /// <summary><c>_STATUSES_UPSTREAM_ACTIVE</c>: shared across every scope.</summary>
    public static readonly IReadOnlySet<string> UpstreamActiveStatuses = new HashSet<string>(StringComparer.Ordinal)
    {
        "downloading", "queued", "paused", "delay", "downloadpending", "downloadclientunavailable", "warning",
    };

    public static readonly QueueDialect MovieQueueDialect = new(
        "movie",
        ["movie", "media", "item"],
        ["title", "originalTitle", "original_title"],
        ["movieId", "movie_id", "entityId", "entity_id"],
        UpstreamActiveStatuses);

    public static readonly QueueDialect TvQueueDialect = new(
        "tv",
        ["series", "show", "media", "item"],
        ["title", "sortTitle", "sort_title"],
        ["seriesId", "series_id", "entityId", "entity_id"],
        UpstreamActiveStatuses);

    /// <summary><c>queue_dialect_for_scope</c>: accepts the common spellings.</summary>
    public static QueueDialect ForScope(string scope)
    {
        return PyStrings.Strip(scope ?? string.Empty).ToLowerInvariant() switch
        {
            "movie" or "movies" => MovieQueueDialect,
            "tv" or "series" => TvQueueDialect,
            _ => throw new ArgumentException($"Unknown media scope for queue dialect: {PyStrings.Repr(scope ?? string.Empty)}", nameof(scope)),
        };
    }

    private static (string? Title, long? Year) QueueTitleAndYear(PyDict row, QueueDialect dialect)
    {
        foreach (var key in dialect.EntityKeys)
        {
            if (row.Get(key) is not PyDict entity)
            {
                continue;
            }

            var title = PyValues.FirstText(entity, [.. dialect.EntityTitleFields]);
            var year = PyValues.FirstNumber(entity, "year");
            if (title is not null)
            {
                return (title, year is { } y ? (long)y : null);
            }
        }

        // Year only ever comes from the nested entity, matching the previous per-vendor behaviour: a
        // top-level year on the row is not trusted to describe the entity.
        return (PyValues.FirstText(row, "title", "name"), null);
    }

    private static bool AppliesToFile(PyDict row, QueueDialect dialect, string? candidatePath, long? candidateEntityId)
    {
        if (QueueRowPlumbing.PathMatchesCandidate(row, candidatePath))
        {
            return true;
        }

        if (candidateEntityId is null)
        {
            return false;
        }

        var rowId = PyValues.FirstNumber(row, [.. dialect.EntityIdFields]);
        return rowId is { } id && (long)id == candidateEntityId;
    }

    /// <summary>
    /// <c>map_queue_row_to_refiner_view</c>. <c>applies_to_file</c>: <c>outputPath</c> matches <paramref name="candidatePath"/>,
    /// and/or the row's scope id field matches <paramref name="candidateEntityId"/>.
    /// </summary>
    public static RefinerQueueRowView MapToView(PyDict row, QueueDialect dialect, string? candidatePath = null, long? candidateEntityId = null)
    {
        ArgumentNullException.ThrowIfNull(row);
        ArgumentNullException.ThrowIfNull(dialect);
        var status = QueueRowPlumbing.PrimaryQueueStatus(row);
        var isImportPending = status == "importpending";
        var isUpstreamActive = dialect.ActiveStatuses.Contains(status) && !isImportPending;
        var (title, year) = QueueTitleAndYear(row, dialect);
        return new RefinerQueueRowView(
            AppliesToFile(row, dialect, candidatePath, candidateEntityId),
            isUpstreamActive,
            isImportPending,
            QueueRowPlumbing.BlockingSuppressedForImportWait(row),
            title,
            year is { } y2 ? (int)y2 : null);
    }
}
