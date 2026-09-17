using System.Globalization;
using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>
/// The phrasing half of <c>weir.platform.media_managers.manager_dialects</c>: each product's JSON read into
/// the neutral port shapes. The HTTP half lives in Weir.Infrastructure.
/// </summary>
public static class ManagerDialectRules
{
    public const string ExternalManifestPath = "/api/integrations/external/manifest";
    public const string ExternalQueuePath = "/api/integrations/external/queue";

    /// <summary>
    /// Deluno's "a tool changed this library file" endpoint (jampat000/Deluno#528, confirmed against the
    /// checkout at commit 177ff18a: <c>src/Deluno.Worker/ExternalFileChangedEndpoints.cs:43</c>). Body is
    /// <c>{"path": "...", "reason": "...", "tool": "Weir"}</c>; it answers 202 Accepted, not one of the
    /// three statuses every other manager call accepts (#507).
    /// </summary>
    public const string ExternalFileChangedPath = "/api/integrations/external/file-changed";

    /// <summary>
    /// The manifest capability Deluno advertises for <see cref="ExternalFileChangedPath"/>
    /// (<c>ExternalIntegrationEndpointRouteBuilderExtensions.cs:108</c>): gate the call on it rather than
    /// trying and classifying a 404, since an older Deluno without #528 has no route there at all.
    /// </summary>
    public const string ExternalFileChangedCapability = "external-file-changed";

    public const int ArrLibraryPageSize = 200_000;
    public const int ArrQueuePageSize = 1000;

    public static readonly TimeSpan QueueTimeout = TimeSpan.FromSeconds(30);
    public static readonly TimeSpan LibraryTimeout = TimeSpan.FromSeconds(120);
    public static readonly TimeSpan DescribeTimeout = TimeSpan.FromSeconds(15);

    private static readonly HashSet<string> SettledStates = new(StringComparer.Ordinal)
    {
        "completed", "complete", "done", "finished", "succeeded", "success", "ok", "failed", "failure", "error",
        "cancelled", "canceled", "aborted", "skipped", "ignored", "rejected",
    };

    private static readonly HashSet<string> ImportPendingStates = new(StringComparer.Ordinal)
    {
        "importing", "importpending", "import_pending", "import-pending", "finalizing", "finalising", "moving", "handoff", "handing_off",
    };

    /// <summary>The outbound <c>_scope_from_media_type</c>.</summary>
    public static string? ScopeFromMediaType(PyJson? raw)
    {
        var value = (PyValues.Text(raw) ?? string.Empty).ToLowerInvariant();
        return value switch
        {
            "movie" or "movies" or "film" or "films" => MediaManagerKinds.Movie,
            "tv" or "series" or "show" or "shows" or "episode" or "episodes" => MediaManagerKinds.Tv,
            _ => null,
        };
    }

    /// <summary><c>_unreachable</c>: one sentence an operator can act on, with the connection named.</summary>
    public static string Unreachable(ManagerConnection connection, Exception exception, string what)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(exception);
        switch (exception)
        {
            case MediaManagerRateLimitedException limited:
                var wait = limited.RetryAfterSeconds;
                var when = wait is { } seconds && seconds != 0
                    ? $" It asked Weir to wait about {Math.Truncate(seconds).ToString("0", CultureInfo.InvariantCulture)}s."
                    : string.Empty;
                return $"{connection.Label} is rate limiting Weir, so it could not say {what}.{when} " +
                       "Weir backed off rather than retrying straight away.";
            case MediaManagerHttpException http:
                var detail = http.Message;
                if (detail.Contains("HTTP 401", StringComparison.Ordinal) || detail.Contains("HTTP 403", StringComparison.Ordinal))
                {
                    return $"{connection.Label} refused Weir's API key, so it could not say {what}. " +
                           "Check the key on the Media managers settings page and save it again.";
                }

                return $"{connection.Label} did not give Weir the answer it expected when asked {what} ({detail}).";
            default:
                return $"Weir could not reach {connection.Label} to ask {what} ({exception.Message}). " +
                       "Check the address is right and that the app is running.";
        }
    }

    /// <summary>
    /// <c>_paths_under</c>. #544 item 4: Python reads the raw value with <c>str(row.get("path", ""))</c>, so a
    /// root folder whose <c>path</c> is JSON <c>null</c> (present but empty) turns into the literal string
    /// <c>"None"</c> and is reported as a root folder called "None" — the default in <c>dict.get</c> only ever
    /// applies when the key is missing, never when it is <c>null</c>. Decision: skip it, the same as a root
    /// folder with no <c>path</c> at all, rather than invent a label for a folder the manager did not name.
    /// This matches the <c>libraries</c> side of <see cref="ArrRootFolders"/>, which already used
    /// <see cref="PyValues.Text"/> and so already dropped these rows; only the <c>roots</c> list disagreed.
    /// </summary>
    public static List<string> ArrRootPaths(IEnumerable<PyDict> rows) =>
        [.. rows.Select(row => PyValues.Text(row.Get("path"))).OfType<string>()];

    /// <summary>The arr <c>describe</c> answer from a <c>/api/v3/rootfolder</c> payload.</summary>
    public static (List<string> Roots, List<ManagerLibraryDescriptor> Libraries) ArrRootFolders(PyJson? payload, string scope)
    {
        var rows = PyValues.Dicts(payload);
        var libraries = new List<ManagerLibraryDescriptor>();
        foreach (var row in rows)
        {
            if (PyValues.Text(row.Get("path")) is not { } path)
            {
                continue;
            }

            var id = PyValues.FirstNumber(row, "id");
            var key = id is { } number && !number.IsZero ? number.ToString(CultureInfo.InvariantCulture) : path;
            libraries.Add(new ManagerLibraryDescriptor(key, path, scope, path));
        }

        return (ArrRootPaths(rows), libraries);
    }

    /// <summary>The arr queue rows: a list, or the <c>records</c> of a paged envelope.</summary>
    public static List<ManagerQueueRow> ArrQueueRows(PyJson? payload, string scope)
    {
        PyJson? records = payload switch
        {
            PyList => payload,
            null or PyNull => null,
            PyDict dict => dict.Get("records"),
            // Python: payload.get("records") on a non-mapping raises AttributeError, answered as a 500.
            _ when !payload.IsTruthy => null,
            _ => throw new InvalidOperationException($"'{payload.PythonTypeName}' object has no attribute 'get'"),
        };
        return [.. PyValues.Dicts(records).Select(row => new ManagerQueueRow(scope, row))];
    }

    /// <summary>Library file paths from <c>/api/v3/movie</c> (nested under <paramref name="fileKey"/>) or <c>/api/v3/episodefile</c>.</summary>
    public static List<string> ArrLibraryFilePaths(PyJson? payload, string? fileKey)
    {
        var paths = new List<string>();
        foreach (var row in PyValues.Dicts(payload))
        {
            var holder = fileKey is null ? row : row.Get(fileKey);
            if (holder is PyDict mapping && PyValues.Text(mapping.Get("path")) is { } found)
            {
                paths.Add(found);
            }
        }

        return paths;
    }

    /// <summary>
    /// list_library_files (#507), the movie half: <c>/api/v3/movie</c> rows carry the title's own id/name and,
    /// when the movie has a file, the embedded <c>movieFile.path</c> (verified: <c>MovieResource</c> and
    /// <c>MovieFileResource</c> in Radarr's <c>openapi.json</c> — a movie with no file simply has no
    /// <c>movieFile</c>, which is skipped rather than treated as a match).
    /// </summary>
    public static List<ManagerLibraryFile> ArrMovieLibraryFiles(PyJson? payload)
    {
        var files = new List<ManagerLibraryFile>();
        foreach (var row in PyValues.Dicts(payload))
        {
            if (PyValues.FirstNumber(row, "id") is not { } id)
            {
                continue;
            }

            if (row.Get("movieFile") is not PyDict file || PyValues.Text(file.Get("path")) is not { } path)
            {
                continue;
            }

            var idText = id.ToString(CultureInfo.InvariantCulture);
            var fileId = PyValues.FirstNumber(file, "id") is { } fileNumber ? (long)fileNumber : (long?)null;
            var qualityProfileId = PyValues.FirstNumber(row, "qualityProfileId") is { } profileNumber ? (long)profileNumber : (long?)null;
            files.Add(new ManagerLibraryFile(idText, PyValues.FirstText(row, "title") ?? idText, path, fileId, qualityProfileId));
        }

        return files;
    }

    /// <summary>
    /// list_library_files (#507), the series half: one series' <c>/api/v3/episodefile?seriesId=</c> rows, each
    /// tagged with the series id/title/quality-profile-id the caller already looked up from <c>/api/v3/series</c>
    /// (verified: Sonarr's <c>EpisodeFileController.GetEpisodeFiles</c> throws <c>BadRequestException</c> without
    /// <c>seriesId</c> or <c>episodeFileIds</c>, so listing every file means walking <c>/api/v3/series</c> first,
    /// one call per series). #551's <see cref="ManagerLibraryFile.FileId"/> is each row's own <c>id</c> — the
    /// individual episode file, not the series.
    /// </summary>
    public static List<ManagerLibraryFile> ArrEpisodeLibraryFiles(PyJson? payload, string seriesId, string seriesTitle, long? seriesQualityProfileId = null)
    {
        var files = new List<ManagerLibraryFile>();
        foreach (var row in PyValues.Dicts(payload))
        {
            if (PyValues.Text(row.Get("path")) is { } path)
            {
                var fileId = PyValues.FirstNumber(row, "id") is { } fileNumber ? (long)fileNumber : (long?)null;
                files.Add(new ManagerLibraryFile(seriesId, seriesTitle, path, fileId, seriesQualityProfileId));
            }
        }

        return files;
    }

    /// <summary>
    /// file_changed (#507)'s <c>POST /api/v3/command</c> shape: the command's own name (matched
    /// case-insensitively against its class name minus "Command" — <c>CommandController.StartCommand</c>) and
    /// its one id property, camelCase (<c>STJson</c>'s <c>JsonNamingPolicy.CamelCase</c>). Verified against
    /// <c>RescanMovieCommand</c>/<c>RescanSeriesCommand</c> in each product's <c>MediaFiles/Commands</c>.
    /// </summary>
    public static (string CommandName, string IdProperty) ArrRescanCommand(string mediaScope) =>
        mediaScope == MediaManagerKinds.Tv ? ("RescanSeries", "seriesId") : ("RescanMovie", "movieId");

    /// <summary><c>_manifest_libraries</c>.</summary>
    public static List<PyDict> ManifestLibraries(PyJson? payload)
    {
        if (payload is PyDict mapping)
        {
            foreach (var key in new[] { "libraries", "roots", "rootFolders", "root_folders", "items" })
            {
                var found = PyValues.Dicts(mapping.Get(key));
                if (found.Count > 0)
                {
                    return found;
                }
            }

            return [];
        }

        return PyValues.Dicts(payload);
    }

    /// <summary><c>_manifest_capabilities</c>: the manifest's capability strings, lower-cased.</summary>
    public static IReadOnlySet<string> ManifestCapabilities(PyJson? payload)
    {
        var set = new SortedSet<string>(StringComparer.Ordinal);
        if (payload is PyDict mapping && mapping.Get("capabilities") is PyList list)
        {
            foreach (var item in list.Items.OfType<PyStr>())
            {
                var text = PyStrings.Strip(item.Value);
                if (text.Length > 0)
                {
                    set.Add(text.ToLowerInvariant());
                }
            }
        }

        return set;
    }

    /// <summary><c>_manifest_library_key</c>.</summary>
    public static string? ManifestLibraryKey(PyDict library)
    {
        ArgumentNullException.ThrowIfNull(library);
        var number = PyValues.FirstNumber(library, "id");
        return number is { } n ? n.ToString(CultureInfo.InvariantCulture) : PyValues.FirstText(library, "id");
    }

    /// <summary><c>_manifest_library_descriptor</c>, read against the confirmed Deluno contract.</summary>
    public static ManagerLibraryDescriptor ManifestLibraryDescriptor(PyDict library)
    {
        ArgumentNullException.ThrowIfNull(library);
        var key = ManifestLibraryKey(library) ?? string.Empty;
        var name = PyValues.FirstText(library, "name") ?? key;
        var scope = ScopeFromMediaType(library.Get("mediaType"));
        var root = PyValues.FirstText(library, "rootPath");
        var workflow = PyStrings.Strip(PyValues.Text(library.Get("importWorkflow")) ?? string.Empty).ToLowerInvariant();
        var processesBeforeImport = workflow == "refine-before-import";
        var output = processesBeforeImport ? PyValues.FirstText(library, "processorOutputPath") : null;
        return new ManagerLibraryDescriptor(key, name, scope, root, output, processesBeforeImport);
    }

    /// <summary>The external-integration <c>describe</c> answer from a manifest payload.</summary>
    public static ManagerDescription ExternalDescription(ManagerConnection connection, ManagerCapabilities staticCapabilities, PyJson? payload)
    {
        ArgumentNullException.ThrowIfNull(staticCapabilities);
        var libraries = ManifestLibraries(payload);
        var scopes = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var library in libraries)
        {
            if (ScopeFromMediaType(PyValues.Or(library.Get("mediaType"), library.Get("media_type"), library.Get("scope"))) is { } scope)
            {
                scopes.Add(scope);
            }
        }

        var roots = libraries
            .Select(library => PyStrings.Strip(PyValues.FirstText(library, "path", "rootFolder", "root_folder", "root") ?? string.Empty))
            .Where(path => path.Length > 0)
            .ToList();
        var capabilities = scopes.Count > 0
            ? new ManagerCapabilities(scopes, staticCapabilities.ReportsQueue, staticCapabilities.ReportsLibraryTruth, staticCapabilities.Summary)
            : staticCapabilities;
        return new ManagerDescription(
            connection,
            SignalStatus.Reported,
            capabilities,
            roots,
            [.. libraries.Where(library => !string.IsNullOrEmpty(ManifestLibraryKey(library))).Select(ManifestLibraryDescriptor)],
            AdvertisedCapabilities: ManifestCapabilities(payload));
    }

    /// <summary><c>_external_queue_entries</c>: every row, whichever container the manager wrapped it in.</summary>
    public static List<PyDict> ExternalQueueEntries(PyJson? payload)
    {
        if (payload is PyList)
        {
            return PyValues.Dicts(payload);
        }

        if (payload is not PyDict mapping)
        {
            return [];
        }

        var collected = new List<PyDict>();
        foreach (var key in new[] { "jobs", "dispatches", "downloads", "queue", "items", "records", "results" })
        {
            collected.AddRange(PyValues.Dicts(mapping.Get(key)));
        }

        return collected;
    }

    /// <summary><c>_external_queue_status</c>: an unrecognised state reads as still in progress.</summary>
    public static string ExternalQueueStatus(PyDict entry)
    {
        var raw = PyValues.FirstText(entry, "status", "state", "jobStatus", "job_status", "phase") ?? string.Empty;
        var value = raw.ToLowerInvariant().Replace(" ", "_", StringComparison.Ordinal);
        if (ImportPendingStates.Contains(value))
        {
            return "importpending";
        }

        return SettledStates.Contains(value) ? value : "downloading";
    }

    /// <summary><c>_external_queue_row</c>: null when the row names no scope.</summary>
    public static ManagerQueueRow? ExternalQueueRow(PyDict entry)
    {
        ArgumentNullException.ThrowIfNull(entry);
        var scope = ScopeFromMediaType(PyValues.Or(
            entry.Get("mediaType"), entry.Get("media_type"), entry.Get("mediaScope"), entry.Get("media_scope"), entry.Get("scope")));
        if (scope is null)
        {
            return null;
        }

        var path = PyValues.FirstText(entry, "outputPath", "output_path", "targetPath", "target_path", "sourcePath", "source_path", "filePath", "file_path", "path");
        var title = PyValues.FirstText(entry, "title", "releaseName", "release_name", "name");
        var payload = new PyDict()
            .Set("status", ExternalQueueStatus(entry))
            .Set("outputPath", path)
            .Set("title", title)
            .Set("media", new PyDict().Set("title", title).Set("year", PyValues.Number(PyValues.FirstNumber(entry, "year", "releaseYear", "release_year"))))
            .Set("entityId", PyValues.Number(PyValues.FirstNumber(entry, "entityId", "entity_id", "mediaId", "media_id", "id")));
        return new ManagerQueueRow(scope, payload);
    }

    /// <summary><c>_only_rows_for_scope</c>: drop rows describing the other kind of library; a silent manager stays silent.</summary>
    public static ManagerQueueSignal OnlyRowsForScope(ManagerQueueSignal signal, string mediaScope)
    {
        ArgumentNullException.ThrowIfNull(signal);
        if (!signal.IsReported)
        {
            return signal;
        }

        var kept = signal.Rows.Where(row => row.Scope == mediaScope).ToList();
        return kept.Count == signal.Rows.Count ? signal : signal with { Rows = kept };
    }
}
