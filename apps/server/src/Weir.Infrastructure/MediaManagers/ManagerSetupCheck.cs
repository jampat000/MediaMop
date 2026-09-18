using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>
/// "Will this media manager pick up what this library writes?" for every enabled Sonarr, Radarr and Deluno connection that
/// covers a media type (<see cref="ManagerSetupRules"/> holds the rules and their Sonarr/Radarr/Deluno citations).
/// </summary>
/// <remarks>
/// Read only, by construction: the only calls are <c>GET</c>s — <see cref="ManagerSetupRules.RemotePathMappingPath"/>,
/// <see cref="ManagerSetupRules.DownloadClientPath"/>, <see cref="ManagerSetupRules.DownloadClientConfigPath"/> and the
/// queue (<see cref="IMediaManagerPort.QueueRowsAsync"/>) for Sonarr/Radarr, and Deluno's manifest through
/// <see cref="IMediaManagerPort.DescribeAsync"/>. Weir never changes a
/// manager's settings; the user makes the mapping, and this says whether it is right.
/// </remarks>
public sealed class ManagerSetupCheck
{
    private readonly MediaManagerConnectionService _connections;
    private readonly IManagerHttpHandlerFactory _handlers;

    public ManagerSetupCheck(MediaManagerConnectionService connections, IManagerHttpHandlerFactory handlers)
    {
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
    }

    /// <summary>One entry per enabled connection that covers <paramref name="mediaScope"/>, in connection order.</summary>
    public async Task<List<PyDict>> CheckAsync(
        UnitOfWork uow, string mediaScope, string watchedFolder, string outputFolder, bool removesOriginals = true, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var results = new List<PyDict>();
        foreach (var row in await MediaManagerConnectionStore.ListEnabledAsync(uow).ConfigureAwait(false))
        {
            var isArr = ManagerKindProfiles.ForKind(row.Kind) is { IsArr: true } profile && profile.ArrScope == mediaScope;
            var isDeluno = string.Equals(row.Kind, "deluno", StringComparison.OrdinalIgnoreCase);
            if (!isArr && !isDeluno)
            {
                continue;
            }

            var label = MediaManagerKinds.LabelForConnection(row.Kind, row.Name);
            var entry = new PyDict()
                .Set("connection_id", row.Id)
                .Set("kind", row.Kind)
                .Set("name", row.Name)
                .Set("label", label)
                .Set("flow", isArr ? "remote_path_mapping" : "handoff");
            IReadOnlyList<SetupCheckLine> lines;
            var connection = _connections.ConnectionFromRow(row);
            if (connection is null)
            {
                lines = [new SetupCheckLine(SetupCheckLine.Problem, $"{label} has no address or API key saved, so Weir cannot check it. Add them under Settings → Media managers.")];
            }
            else if (isArr)
            {
                (var hosts, lines) = await CheckArrAsync(connection, mediaScope, watchedFolder, outputFolder, removesOriginals, cancellationToken).ConfigureAwait(false);
                entry.Set("mapping", new PyDict()
                    .Set("hosts", new PyList(hosts.Select(host => (PyJson)new PyStr(host))))
                    .Set("remote_path", PyStrings.Strip(watchedFolder))
                    .Set("local_path", PyStrings.Strip(outputFolder)));
            }
            else
            {
                var deluno = await CheckDelunoAsync(connection, label, mediaScope, watchedFolder, outputFolder, cancellationToken).ConfigureAwait(false);
                lines = deluno.Lines;
                entry.Set("suggested_watched_folder", deluno.WatchedFolder).Set("suggested_output_folder", deluno.OutputFolder);
            }

            entry.Set("ready", lines.All(line => line.State != SetupCheckLine.Problem));
            entry.Set("lines", new PyList(lines.Select(line => (PyJson)line.ToOut())));
            results.Add(entry);
        }

        return results;
    }

    private async Task<(IReadOnlyList<string> Hosts, IReadOnlyList<SetupCheckLine> Lines)> CheckArrAsync(
        ManagerConnection connection, string mediaScope, string watchedFolder, string outputFolder, bool removesOriginals, CancellationToken cancellationToken)
    {
        PyJson? mappings;
        PyJson? clients;
        try
        {
            var client = new MediaManagerHttpClient(connection.BaseUrl, connection.ApiKey, _handlers, ManagerDialectRules.DescribeTimeout);
            mappings = await client.GetJsonAsync(ManagerSetupRules.RemotePathMappingPath, cancellationToken: cancellationToken).ConfigureAwait(false);
            clients = await client.GetJsonAsync(ManagerSetupRules.DownloadClientPath, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return ([], [new SetupCheckLine(SetupCheckLine.Problem, ManagerDialectRules.Unreachable(connection, exception, "its remote path mappings"))]);
        }

        var result = ManagerSetupRules.EvaluateArr(
            connection.Label,
            mediaScope,
            watchedFolder,
            outputFolder,
            ManagerSetupRules.ParseMappings(mappings),
            ManagerSetupRules.ParseDownloadClients(clients, mediaScope),
            await CompletedDownloadHandlingAsync(connection, cancellationToken).ConfigureAwait(false),
            await QueueOutputPathsAsync(connection, cancellationToken).ConfigureAwait(false),
            removesOriginals);
        return (result.Hosts, result.Lines);
    }

    /// <summary>Queued downloads' <c>outputPath</c>s, through the port's own queue read; none when the queue cannot be read.</summary>
    private async Task<IReadOnlyList<string>> QueueOutputPathsAsync(ManagerConnection connection, CancellationToken cancellationToken)
    {
        if (_connections.Ports.PortForKind(connection.Kind) is not { } port)
        {
            return [];
        }

        var signal = await port.QueueRowsAsync(connection, cancellationToken).ConfigureAwait(false);
        return signal.IsReported
            ? [.. signal.Rows.Select(row => PyValues.FirstText(row.Payload, "outputPath")).OfType<string>()]
            : [];
    }

    /// <summary><c>enableCompletedDownloadHandling</c>, or null when it cannot be read: a missing answer is not a problem.</summary>
    private async Task<bool?> CompletedDownloadHandlingAsync(ManagerConnection connection, CancellationToken cancellationToken)
    {
        try
        {
            var client = new MediaManagerHttpClient(connection.BaseUrl, connection.ApiKey, _handlers, ManagerDialectRules.DescribeTimeout);
            return await client.GetJsonAsync(ManagerSetupRules.DownloadClientConfigPath, cancellationToken: cancellationToken).ConfigureAwait(false) is PyDict config &&
                   config.Get("enableCompletedDownloadHandling") is PyBool flag
                ? flag.Value
                : null;
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or MediaManagerUnreachableException)
        {
            return null;
        }
    }

    private async Task<DelunoSetupResult> CheckDelunoAsync(
        ManagerConnection connection, string label, string mediaScope, string watchedFolder, string outputFolder, CancellationToken cancellationToken)
    {
        if (_connections.Ports.PortForKind(connection.Kind) is not { } port)
        {
            return new DelunoSetupResult(null, null, [new SetupCheckLine(SetupCheckLine.Problem, $"Weir does not know how to ask {label} what it manages.")]);
        }

        var description = await port.DescribeAsync(connection, cancellationToken).ConfigureAwait(false);
        return description.Status != SignalStatus.Reported
            ? new DelunoSetupResult(null, null, [new SetupCheckLine(SetupCheckLine.Problem, description.Detail ?? $"{label} did not answer.")])
            : ManagerSetupRules.EvaluateDeluno(label, mediaScope, watchedFolder, outputFolder, description.Libraries);
    }
}
