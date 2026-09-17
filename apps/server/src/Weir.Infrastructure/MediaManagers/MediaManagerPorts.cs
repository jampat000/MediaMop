using System.Globalization;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.MediaManagers;

namespace Weir.Infrastructure.MediaManagers;

/// <summary><c>port_for_kind</c>: the outbound dialect for a kind, or null for a kind Weir does not know.</summary>
public interface IMediaManagerPorts
{
    IMediaManagerPort? PortForKind(string? kind);
}

/// <summary>The four ports over HTTP (port of <c>manager_dialects._PORTS</c>).</summary>
public sealed class HttpMediaManagerPorts : IMediaManagerPorts
{
    private readonly IManagerHttpHandlerFactory _handlers;

    public HttpMediaManagerPorts(IManagerHttpHandlerFactory handlers)
    {
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
    }

    public IMediaManagerPort? PortForKind(string? kind) =>
        ManagerKindProfiles.ForKind(kind) is { } profile ? new HttpMediaManagerPort(profile, _handlers) : null;

    /// <summary>
    /// <c>environment_connection_for_scope</c>: the <c>WEIR_ARR_*</c> credentials that predate the connections table.
    /// </summary>
    public static ManagerConnection? EnvironmentConnectionForScope(WeirOptions options, string mediaScope)
    {
        ArgumentNullException.ThrowIfNull(options);
        var (url, key, kind) = mediaScope == MediaManagerKinds.Tv
            ? (options.ArrSonarrBaseUrl, options.ArrSonarrApiKey, "sonarr")
            : (options.ArrRadarrBaseUrl, options.ArrRadarrApiKey, "radarr");
        return string.IsNullOrEmpty(url) || string.IsNullOrEmpty(key)
            ? null
            : new ManagerConnection(kind, "from environment", url, key);
    }
}

/// <summary><c>ArrV3ManagerPort</c> and <c>ExternalIntegrationManagerPort</c>, chosen by the kind's profile.</summary>
public sealed class HttpMediaManagerPort : IMediaManagerPort
{
    private readonly ManagerKindProfile _profile;
    private readonly IManagerHttpHandlerFactory _handlers;

    public HttpMediaManagerPort(ManagerKindProfile profile, IManagerHttpHandlerFactory handlers)
    {
        _profile = profile ?? throw new ArgumentNullException(nameof(profile));
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
    }

    public string Kind => _profile.Kind;

    public ManagerCapabilities Capabilities() => _profile.Capabilities;

    public async Task<ManagerDescription> DescribeAsync(ManagerConnection connection, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        var capabilities = Capabilities();
        var path = _profile.IsArr ? "/api/v3/rootfolder" : ManagerDialectRules.ExternalManifestPath;
        PyJson? payload;
        try
        {
            payload = await Client(connection, ManagerDialectRules.DescribeTimeout).GetJsonAsync(path, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return new ManagerDescription(
                connection,
                SignalStatus.Unreachable,
                capabilities,
                [],
                [],
                ManagerDialectRules.Unreachable(connection, exception, _profile.IsArr ? "which folders it manages" : "what it manages"),
                new SortedSet<string>(StringComparer.Ordinal));
        }

        if (!_profile.IsArr)
        {
            return ManagerDialectRules.ExternalDescription(connection, capabilities, payload);
        }

        var (roots, libraries) = ManagerDialectRules.ArrRootFolders(payload, _profile.ArrScope!);
        return new ManagerDescription(connection, SignalStatus.Reported, capabilities, roots, libraries, AdvertisedCapabilities: new SortedSet<string>(StringComparer.Ordinal));
    }

    public async Task<ManagerQueueSignal> QueueRowsAsync(ManagerConnection connection, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        PyJson? payload;
        try
        {
            var client = Client(connection, ManagerDialectRules.QueueTimeout);
            payload = _profile.IsArr
                ? await client.GetJsonAsync("/api/v3/queue", [new("pageSize", ManagerDialectRules.ArrQueuePageSize)], cancellationToken).ConfigureAwait(false)
                : await client.GetJsonAsync(ManagerDialectRules.ExternalQueuePath, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return new ManagerQueueSignal(connection, SignalStatus.Unreachable, [], ManagerDialectRules.Unreachable(connection, exception, "what it is importing"));
        }

        if (_profile.IsArr)
        {
            return new ManagerQueueSignal(connection, SignalStatus.Reported, ManagerDialectRules.ArrQueueRows(payload, _profile.ArrScope!));
        }

        var rows = ManagerDialectRules.ExternalQueueEntries(payload)
            .Select(ManagerDialectRules.ExternalQueueRow)
            .OfType<ManagerQueueRow>()
            .ToList();
        return new ManagerQueueSignal(connection, SignalStatus.Reported, rows);
    }

    public async Task RemoveQueueItemAsync(ManagerConnection connection, PyDict row, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(row);
        if (!_profile.IsArr)
        {
            throw new MediaManagerHttpException(
                $"{connection.Label} takes a rejection through its hand-off report, not by removing a queue item.");
        }

        var queueId = PyValues.FirstNumber(row, "id")
            ?? throw new MediaManagerHttpException($"{connection.Label}'s queue item has no id.");
        await Client(connection, ManagerDialectRules.QueueTimeout).DeleteAsync(
            $"/api/v3/queue/{queueId.ToString(CultureInfo.InvariantCulture)}",
            [new("removeFromClient", true), new("blocklist", true)],
            cancellationToken).ConfigureAwait(false);
    }

    public async Task<ManagerLibraryTruth> LibraryTruthAsync(ManagerConnection connection, string mediaScope, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        if (!_profile.IsArr)
        {
            return new ManagerLibraryTruth(
                connection,
                SignalStatus.NoSignal,
                [],
                $"{connection.Label} tells Weir what it manages and what it is importing, but not which " +
                "individual files it still keeps, so it cannot clear a folder for deletion.");
        }

        if (mediaScope != _profile.ArrScope)
        {
            return new ManagerLibraryTruth(connection, SignalStatus.NoSignal, [], $"{connection.Label} does not look after this kind of library.");
        }

        PyJson? payload;
        try
        {
            payload = await Client(connection, ManagerDialectRules.LibraryTimeout)
                .GetJsonAsync(_profile.ArrLibraryPath!, [new("pageSize", ManagerDialectRules.ArrLibraryPageSize)], cancellationToken)
                .ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return new ManagerLibraryTruth(connection, SignalStatus.Unreachable, [], ManagerDialectRules.Unreachable(connection, exception, "which files it still keeps"));
        }

        return new ManagerLibraryTruth(connection, SignalStatus.Reported, ManagerDialectRules.ArrLibraryFilePaths(payload, _profile.ArrFileKey));
    }

    public async Task<ManagerLibraryFilesSignal> ListLibraryFilesAsync(ManagerConnection connection, string mediaScope, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        if (!_profile.IsArr)
        {
            return new ManagerLibraryFilesSignal(
                connection,
                SignalStatus.NoSignal,
                [],
                $"{connection.Label} does not offer a file-by-file library listing Weir can match to a title.");
        }

        if (mediaScope != _profile.ArrScope)
        {
            return new ManagerLibraryFilesSignal(connection, SignalStatus.NoSignal, [], $"{connection.Label} does not look after this kind of library.");
        }

        var client = Client(connection, ManagerDialectRules.LibraryTimeout);
        try
        {
            if (mediaScope == MediaManagerKinds.Movie)
            {
                var payload = await client.GetJsonAsync("/api/v3/movie", [new("pageSize", ManagerDialectRules.ArrLibraryPageSize)], cancellationToken).ConfigureAwait(false);
                return new ManagerLibraryFilesSignal(connection, SignalStatus.Reported, ManagerDialectRules.ArrMovieLibraryFiles(payload));
            }

            // Sonarr has no "every episode file" endpoint: EpisodeFileController.GetEpisodeFiles requires
            // seriesId or episodeFileIds, so every series is listed first and asked for its files in turn.
            var seriesPayload = await client.GetJsonAsync("/api/v3/series", [new("pageSize", ManagerDialectRules.ArrLibraryPageSize)], cancellationToken).ConfigureAwait(false);
            var files = new List<ManagerLibraryFile>();
            foreach (var series in PyValues.Dicts(seriesPayload))
            {
                if (PyValues.FirstNumber(series, "id") is not { } seriesId)
                {
                    continue;
                }

                var idText = seriesId.ToString(CultureInfo.InvariantCulture);
                var title = PyValues.FirstText(series, "title") ?? idText;
                var episodePayload = await client.GetJsonAsync("/api/v3/episodefile", [new("seriesId", seriesId)], cancellationToken).ConfigureAwait(false);
                files.AddRange(ManagerDialectRules.ArrEpisodeLibraryFiles(episodePayload, idText, title));
            }

            return new ManagerLibraryFilesSignal(connection, SignalStatus.Reported, files);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return new ManagerLibraryFilesSignal(connection, SignalStatus.Unreachable, [], ManagerDialectRules.Unreachable(connection, exception, "which files it keeps and their titles"));
        }
    }

    public async Task<ManagerNotifyOutcome> FileChangedAsync(
        ManagerConnection connection,
        IReadOnlySet<string> advertisedCapabilities,
        string? titleId,
        string filePath,
        string? reason,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(connection);
        ArgumentNullException.ThrowIfNull(advertisedCapabilities);
        ArgumentNullException.ThrowIfNull(filePath);
        var client = Client(connection, ManagerDialectRules.QueueTimeout);
        if (_profile.IsArr)
        {
            if (titleId is null || !long.TryParse(titleId, NumberStyles.Integer, CultureInfo.InvariantCulture, out var id))
            {
                throw new MediaManagerHttpException($"{connection.Label} needs a matched title id to rescan {filePath}, and none was given.");
            }

            var (name, idProperty) = ManagerDialectRules.ArrRescanCommand(_profile.ArrScope!);
            await client.PostJsonAsync("/api/v3/command", new PyDict().Set("name", name).Set(idProperty, id), cancellationToken: cancellationToken).ConfigureAwait(false);
            return ManagerNotifyOutcome.Notified;
        }

        if (!advertisedCapabilities.Contains(ManagerDialectRules.ExternalFileChangedCapability))
        {
            return ManagerNotifyOutcome.NotSupported;
        }

        var body = new PyDict().Set("path", filePath).Set("tool", "Weir");
        if (!string.IsNullOrEmpty(reason))
        {
            body.Set("reason", reason);
        }

        // Deluno answers 202 Accepted (a queued re-read), not one of the three statuses every other call here accepts.
        await client.PostJsonAsync(ManagerDialectRules.ExternalFileChangedPath, body, acceptedStatuses: [200, 201, 202, 204], cancellationToken: cancellationToken).ConfigureAwait(false);
        return ManagerNotifyOutcome.Notified;
    }

    private MediaManagerHttpClient Client(ManagerConnection connection, TimeSpan timeout) =>
        new(connection.BaseUrl, connection.ApiKey, _handlers, timeout);
}
