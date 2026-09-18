using System.Globalization;
using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>
/// Sonarr/Radarr's own path comparison (<c>NzbDrone.Common/Disk/OsPath.cs</c>, identical on Sonarr develop, Sonarr
/// v5-develop and Radarr develop), mirrored so Weir judges a remote path mapping exactly the way the manager will apply it.
/// </summary>
/// <remarks>
/// <list type="bullet">
/// <item>Kind (<c>DetectPathKind</c>, L43-61): a path starting with <c>/</c> is Unix; otherwise a drive letter or any
/// <c>\</c> makes it Windows; otherwise any <c>/</c> makes it Unix; otherwise it is unknown.</item>
/// <item>Rooted (<c>IsRooted</c>, L133-149): Windows needs <c>\\</c> or a drive letter, Unix a leading <c>/</c>, unknown
/// never is.</item>
/// <item>Contains (<c>Contains</c>, L344-370): both rooted; split on both separators with empty segments dropped
/// (<c>GetFragments</c>, L294-297), so trailing and doubled slashes never matter; the other path has at least as many
/// segments and starts with every one of these; segments compare ignoring case only when either path is a Windows path
/// (L359). So on Linux <c>/Media</c> and <c>/media</c> differ, and <c>/downloads/complete2</c> is not inside
/// <c>/downloads/complete</c>.</item>
/// </list>
/// </remarks>
public readonly record struct ArrOsPath(string Text)
{
    private static readonly char[] Separators = ['\\', '/'];

    public bool IsWindows => Kind == PathKind.Windows;

    public PathKind Kind
    {
        get
        {
            var path = Text ?? string.Empty;
            if (path.StartsWith('/'))
            {
                return PathKind.Unix;
            }

            if (HasDriveLetter(path) || path.Contains('\\', StringComparison.Ordinal))
            {
                return PathKind.Windows;
            }

            return path.Contains('/', StringComparison.Ordinal) ? PathKind.Unix : PathKind.Unknown;
        }
    }

    public bool IsRooted => Kind switch
    {
        PathKind.Windows => (Text ?? string.Empty).StartsWith(@"\\", StringComparison.Ordinal) || HasDriveLetter(Text ?? string.Empty),
        PathKind.Unix => (Text ?? string.Empty).StartsWith('/'),
        _ => false,
    };

    public string[] Segments => (Text ?? string.Empty).Split(Separators, StringSplitOptions.RemoveEmptyEntries);

    /// <summary><c>OsPath.Contains</c>: this path is <paramref name="other"/> or one of its parent folders.</summary>
    public bool Contains(ArrOsPath other)
    {
        if (!IsRooted || !other.IsRooted)
        {
            return false;
        }

        var left = Segments;
        var right = other.Segments;
        if (right.Length < left.Length)
        {
            return false;
        }

        var comparison = Comparison(this, other);
        for (var i = 0; i < left.Length; i++)
        {
            if (!string.Equals(left[i], right[i], comparison))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>The same folder by <c>Contains</c> both ways: Sonarr never compares two whole paths in this flow.</summary>
    public bool SameFolder(ArrOsPath other) => Contains(other) && other.Contains(this);

    /// <summary>
    /// <c>LocalPath + (path - RemotePath)</c> (<c>RemotePathMappingService.RemapRemoteToLocal</c> L144): where a path the
    /// download client reports ends up once the mapping is applied. Only meaningful when <paramref name="remote"/> contains
    /// this path.
    /// </summary>
    public ArrOsPath Remap(ArrOsPath remote, ArrOsPath local)
    {
        var rest = Segments.Skip(remote.Segments.Length).ToArray();
        var root = local.Text.TrimEnd('\\', '/');
        if (root.Length == 0)
        {
            return local;
        }

        var separator = local.IsWindows ? "\\" : "/";
        return new ArrOsPath(rest.Length == 0 ? root : root + separator + string.Join(separator, rest));
    }

    public override string ToString() => Text ?? string.Empty;

    // Sonarr compares with the invariant culture (OsPath.cs L359), not ordinally; kept identical on purpose.
#pragma warning disable CA1309
    private static StringComparison Comparison(ArrOsPath left, ArrOsPath right) =>
        left.IsWindows || right.IsWindows ? StringComparison.InvariantCultureIgnoreCase : StringComparison.InvariantCulture;
#pragma warning restore CA1309

    private static bool HasDriveLetter(string path) =>
        path.Length >= 2 && char.IsLetter(path[0]) && path[1] == ':' && (path.Length == 2 || path[2] is '\\' or '/');

    public enum PathKind
    {
        Unknown,
        Windows,
        Unix,
    }
}

/// <summary>One of the manager's remote path mappings (<c>GET /api/v3/remotepathmapping</c>).</summary>
public sealed record RemotePathMappingEntry(string Host, string RemotePath, string LocalPath);

/// <summary>One download client the manager uses (<c>GET /api/v3/downloadclient</c>), reduced to what the check reads.</summary>
public sealed record ArrDownloadClientEntry(
    string Name, string Implementation, bool Enabled, string? Host, string? Category, string? Directory, string? Protocol = null)
{
    /// <summary><c>protocol</c> is the camelCased <c>DownloadProtocol</c>: <c>torrent</c> or <c>usenet</c>.</summary>
    public bool IsTorrent => string.Equals(Protocol, "torrent", StringComparison.OrdinalIgnoreCase);
}

/// <summary>One line of a setup check: fine, a problem with its fix, or a note worth reading.</summary>
public sealed record SetupCheckLine(string State, string Text)
{
    public const string Ok = "ok";
    public const string Problem = "problem";
    public const string Note = "note";

    public PyDict ToOut() => new PyDict().Set("state", State).Set("text", Text);
}

/// <summary>What a Sonarr/Radarr check found: the hosts to map, and the lines to show.</summary>
public sealed record ArrSetupResult(IReadOnlyList<string> Hosts, IReadOnlyList<SetupCheckLine> Lines);

/// <summary>What a Deluno check found: the folders it reports for this media type, and the lines to show.</summary>
public sealed record DelunoSetupResult(string? WatchedFolder, string? OutputFolder, IReadOnlyList<SetupCheckLine> Lines);

/// <summary>
/// The pure half of "does this media manager pick up what this library writes". Read only: nothing here, or in the code
/// that fetches its inputs, ever writes to a manager's settings.
/// </summary>
public static class ManagerSetupRules
{
    public const string RemotePathMappingPath = "/api/v3/remotepathmapping";
    public const string DownloadClientPath = "/api/v3/downloadclient";
    public const string DownloadClientConfigPath = "/api/v3/config/downloadclient";

    /// <summary>
    /// <c>GET /api/v3/remotepathmapping</c>: <c>host</c>, <c>remotePath</c>, <c>localPath</c>, camelCased by STJson
    /// (Sonarr develop <c>Sonarr.Api.V3/RemotePathMappings/RemotePathMappingResource.cs</c> L10-12; the same in v5-develop's
    /// v3 API and in Radarr). Kept in the manager's own order: the first mapping that matches wins
    /// (<c>RemotePathMappingService.cs</c> L139-148).
    /// </summary>
    public static List<RemotePathMappingEntry> ParseMappings(PyJson? payload) =>
        [.. PyValues.Dicts(payload)
            .Select(row => new RemotePathMappingEntry(
                PyValues.FirstText(row, "host") ?? string.Empty,
                PyValues.FirstText(row, "remotePath") ?? string.Empty,
                PyValues.FirstText(row, "localPath") ?? string.Empty))
            .Where(mapping => mapping.RemotePath.Length > 0)];

    /// <summary>
    /// <c>GET /api/v3/downloadclient</c>: each client's settings arrive as <c>fields[]</c> named by the setting with its first
    /// letter lowercased (<c>Sonarr.Http/ClientSchema/SchemaBuilder.cs</c> L134, L344-347). Every client passes
    /// <c>Settings.Host</c> to the mapping lookup, so <c>host</c> is what a mapping's Host has to match. The category field is
    /// <c>tvCategory</c> in Sonarr and <c>movieCategory</c> in Radarr; a directory, when a client has one, is
    /// <c>tvDirectory</c>/<c>movieDirectory</c> (Transmission, rTorrent) or Deluge's <c>completedDirectory</c>.
    /// </summary>
    public static List<ArrDownloadClientEntry> ParseDownloadClients(PyJson? payload, string mediaScope)
    {
        var categoryField = mediaScope == MediaManagerKinds.Tv ? "tvCategory" : "movieCategory";
        var directoryField = mediaScope == MediaManagerKinds.Tv ? "tvDirectory" : "movieDirectory";
        var clients = new List<ArrDownloadClientEntry>();
        foreach (var row in PyValues.Dicts(payload))
        {
            var fields = PyValues.Dicts(row.Get("fields"))
                .Where(field => PyValues.Text(field.Get("name")) is not null)
                .GroupBy(field => PyValues.Text(field.Get("name"))!, StringComparer.Ordinal)
                .ToDictionary(group => group.Key, group => PyValues.Text(group.First().Get("value")), StringComparer.Ordinal);
            clients.Add(new ArrDownloadClientEntry(
                PyValues.FirstText(row, "name") ?? PyValues.FirstText(row, "implementationName") ?? "Download client",
                PyValues.FirstText(row, "implementation") ?? string.Empty,
                row.Get("enable") is not PyBool { Value: false },
                fields.GetValueOrDefault("host"),
                fields.GetValueOrDefault(categoryField),
                fields.GetValueOrDefault(directoryField) ?? fields.GetValueOrDefault("completedDirectory"),
                PyValues.FirstText(row, "protocol")));
        }

        return clients;
    }

    /// <summary>
    /// Whether the manager will look for this library's downloads in its output folder. Completed Download Handling
    /// rewrites the path a download client reports with the first mapping whose Host matches the client's Host
    /// (ignoring case) and whose Remote Path contains that path, as <c>LocalPath + (path - RemotePath)</c>
    /// (<c>RemotePathMappingService.cs</c> L139-148). For Weir's output to be the place it looks, a mapping has to
    /// rewrite the watched folder to the output folder.
    /// </summary>
    public static ArrSetupResult EvaluateArr(
        string managerLabel,
        string mediaScope,
        string watchedFolder,
        string outputFolder,
        IReadOnlyList<RemotePathMappingEntry> mappings,
        IReadOnlyList<ArrDownloadClientEntry> clients,
        bool? completedDownloadHandling,
        IReadOnlyList<string>? queueOutputPaths = null,
        bool removesOriginals = false)
    {
        ArgumentNullException.ThrowIfNull(mappings);
        ArgumentNullException.ThrowIfNull(clients);
        var lines = new List<SetupCheckLine>();
        var watched = new ArrOsPath(PyStrings.Strip(watchedFolder ?? string.Empty));
        var output = new ArrOsPath(PyStrings.Strip(outputFolder ?? string.Empty));
        var enabled = clients.Where(client => client.Enabled).ToList();
        var hosts = enabled.Select(client => PyStrings.Strip(client.Host ?? string.Empty))
            .Where(host => host.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        if (!watched.IsRooted || !output.IsRooted)
        {
            lines.Add(new SetupCheckLine(SetupCheckLine.Problem, "Set this library's watched and output folders first; the mapping is built from them."));
            return new ArrSetupResult(hosts, lines);
        }

        if (completedDownloadHandling == false)
        {
            lines.Add(new SetupCheckLine(
                SetupCheckLine.Problem,
                $"Completed Download Handling is off in {managerLabel}, so it will never import from Weir's output. Turn it on under Settings → Download Clients."));
        }
        else if (completedDownloadHandling == true)
        {
            lines.Add(new SetupCheckLine(SetupCheckLine.Ok, $"Completed Download Handling is on in {managerLabel}."));
        }

        if (enabled.Count == 0)
        {
            lines.Add(new SetupCheckLine(SetupCheckLine.Problem, $"{managerLabel} has no enabled download client, so it has no downloads to import."));
            return new ArrSetupResult(hosts, lines);
        }

        // Weir removing a seeding torrent's files makes qBittorrent report missingFiles, which Sonarr/Radarr read as
        // a warning (Download/Clients/QBittorrent/QBittorrent.cs L281-283) — and Completed Download Handling only imports
        // a download the client reports as completed (Download/CompletedDownloadService.cs L68), so the import never
        // happens. A usenet download is not seeded, so removing it is fine.
        if (removesOriginals && enabled.Any(client => client.IsTorrent))
        {
            lines.Add(new SetupCheckLine(
                SetupCheckLine.Problem,
                $"Your download client seeds torrents. Turn off \"After cleaning, remove the original download\" so seeding keeps working and {managerLabel} can import."));
        }

        lines.AddRange(MappingLines(managerLabel, watched, output, mappings, hosts));
        lines.AddRange(ClientFolderLines(managerLabel, watched, enabled));
        lines.AddRange(QueueLines(managerLabel, watched, output, queueOutputPaths ?? []));
        return new ArrSetupResult(hosts, lines);
    }

    /// <summary>
    /// The live evidence: a queued download's <c>outputPath</c> is the client's path with the mapping already applied
    /// (<c>Queue/QueueService.cs</c> L82 reads the item's <c>OutputPath</c>, which each client remapped, e.g.
    /// <c>QBittorrent.cs</c> L314-318). One under the output folder shows the mapping working; one still under the watched
    /// folder shows it is not being applied to that download.
    /// </summary>
    private static IEnumerable<SetupCheckLine> QueueLines(string managerLabel, ArrOsPath watched, ArrOsPath output, IReadOnlyList<string> queueOutputPaths)
    {
        var paths = queueOutputPaths.Select(path => new ArrOsPath(PyStrings.Strip(path))).Where(path => path.IsRooted).ToList();
        var unmapped = paths.FirstOrDefault(path => watched.Contains(path) && !output.Contains(path));
        if (unmapped.Text is not null)
        {
            yield return new SetupCheckLine(
                SetupCheckLine.Problem,
                $"{managerLabel} is still looking for a download in {unmapped}, inside the watched folder rather than Weir's output, so no mapping is being applied to it.");
        }

        var mapped = paths.Count(path => output.Contains(path));
        if (mapped > 0)
        {
            yield return new SetupCheckLine(
                SetupCheckLine.Ok,
                mapped == 1
                    ? $"A download in {managerLabel}'s queue already points at Weir's output folder."
                    : $"{mapped.ToString(CultureInfo.InvariantCulture)} downloads in {managerLabel}'s queue already point at Weir's output folder.");
        }
    }

    private static IEnumerable<SetupCheckLine> MappingLines(
        string managerLabel, ArrOsPath watched, ArrOsPath output, IReadOnlyList<RemotePathMappingEntry> mappings, List<string> hosts)
    {
        // Every mapping that touches the watched folder: it covers the whole folder (Remote Path at or above it) or part
        // of it (Remote Path inside it, e.g. one category folder).
        var touching = mappings
            .Where(mapping => new ArrOsPath(mapping.RemotePath) is var remote && (remote.Contains(watched) || watched.Contains(remote)))
            .ToList();
        var forClient = touching.Where(mapping => hosts.Contains(PyStrings.Strip(mapping.Host), StringComparer.InvariantCultureIgnoreCase)).ToList();

        if (forClient.Count == 0)
        {
            if (touching.Count > 0 && hosts.Count > 0)
            {
                var mapping = touching[0];
                yield return new SetupCheckLine(
                    SetupCheckLine.Problem,
                    $"{managerLabel} maps {mapping.RemotePath} for the host \"{mapping.Host}\", but its download client's Host is " +
                    $"{Quoted(hosts)}. The mapping's Host has to match it exactly — change it to {Quoted(hosts)}.");
                yield break;
            }

            yield return new SetupCheckLine(
                SetupCheckLine.Problem,
                $"{managerLabel} has no remote path mapping for {watched} yet — add the one above.");
            yield break;
        }

        foreach (var host in hosts.Where(host => !forClient.Any(mapping => string.Equals(PyStrings.Strip(mapping.Host), host, StringComparison.InvariantCultureIgnoreCase))))
        {
            yield return new SetupCheckLine(
                SetupCheckLine.Problem,
                $"The download client at \"{host}\" has no mapping for {watched} — add the same mapping with Host \"{host}\".");
        }

        foreach (var mapping in forClient.GroupBy(mapping => PyStrings.Strip(mapping.Host), StringComparer.InvariantCultureIgnoreCase).Select(group => group.First()))
        {
            var remote = new ArrOsPath(mapping.RemotePath);
            var local = new ArrOsPath(mapping.LocalPath);
            // Where this mapping sends what the client reports, compared with where Weir writes the same thing.
            var (reported, expected) = remote.Contains(watched)
                ? (watched.Remap(remote, local), output)
                : (remote.Remap(remote, local), remote.Remap(watched, output));
            if (reported.SameFolder(expected))
            {
                yield return new SetupCheckLine(
                    SetupCheckLine.Ok,
                    $"{managerLabel} maps {mapping.RemotePath} to {mapping.LocalPath} for \"{mapping.Host}\", so it looks for these downloads in Weir's output folder.");
            }
            else
            {
                yield return new SetupCheckLine(
                    SetupCheckLine.Problem,
                    $"{managerLabel} maps {mapping.RemotePath} to {mapping.LocalPath}, so it will look for these downloads in {reported}, " +
                    $"not in Weir's output folder {expected}. Change that mapping's Local Path to match the one above.");
            }
        }
    }

    private static IEnumerable<SetupCheckLine> ClientFolderLines(string managerLabel, ArrOsPath watched, IReadOnlyList<ArrDownloadClientEntry> clients)
    {
        foreach (var client in clients)
        {
            var directory = PyStrings.Strip(client.Directory ?? string.Empty);
            if (directory.Length > 0 && new ArrOsPath(directory) is var folder && folder.IsRooted)
            {
                yield return watched.Contains(folder)
                    ? new SetupCheckLine(SetupCheckLine.Ok, $"{client.Name} saves {managerLabel}'s downloads to {directory}, inside Weir's watched folder.")
                    : new SetupCheckLine(
                        SetupCheckLine.Problem,
                        $"{client.Name} saves {managerLabel}'s downloads to {directory}, which is not inside Weir's watched folder {watched}. " +
                        "Point one at the other, or Weir will never see them.");
                continue;
            }

            var category = PyStrings.Strip(client.Category ?? string.Empty);
            if (category.Length > 0 && !watched.Segments.Contains(category, StringComparer.OrdinalIgnoreCase))
            {
                yield return new SetupCheckLine(
                    SetupCheckLine.Note,
                    $"{client.Name} files {managerLabel}'s downloads under the category \"{category}\". {managerLabel} does not say where " +
                    $"that category saves, so make sure its folder is {watched} or inside it.");
            }
        }
    }

    /// <summary>
    /// Deluno hands each finished download to Weir over its API and imports the result itself, so nothing needs mapping.
    /// What Weir can read reliably from its manifest (<c>GET /api/integrations/external/manifest</c>) is each library's
    /// workflow, its <c>downloadsPath</c> ("downloads arrive in") and its <c>processorOutputPath</c>. A hand-off's file
    /// has to sit inside the watched folder (<see cref="HandoffPaths.RelativeMediaPathForHandoff"/>), compared the same
    /// case- and separator-insensitive way here.
    /// </summary>
    public static DelunoSetupResult EvaluateDeluno(
        string managerLabel, string mediaScope, string watchedFolder, string outputFolder, IReadOnlyList<ManagerLibraryDescriptor> libraries)
    {
        ArgumentNullException.ThrowIfNull(libraries);
        var scopeWord = mediaScope == MediaManagerKinds.Tv ? "TV" : "movie";
        var lines = new List<SetupCheckLine>();
        var refining = libraries.Where(library => library.MediaScope == mediaScope && library.ProcessesBeforeImport).ToList();
        if (refining.Count == 0)
        {
            lines.Add(new SetupCheckLine(
                SetupCheckLine.Problem,
                $"No {managerLabel} {scopeWord} library is set to Refine before import, so {managerLabel} will not hand {scopeWord} downloads to Weir. " +
                $"Choose Refine before import for that library in {managerLabel}."));
            return new DelunoSetupResult(null, null, lines);
        }

        var library = refining[0];
        if (refining.Count > 1)
        {
            lines.Add(new SetupCheckLine(
                SetupCheckLine.Note,
                $"{managerLabel} has {refining.Count} {scopeWord} libraries set to Refine before import; the folders below are {library.Name}'s. " +
                "Give each its own Weir library."));
        }

        var downloads = PyStrings.Strip(library.DownloadsPath ?? string.Empty);
        var watched = PyStrings.Strip(watchedFolder ?? string.Empty);
        if (downloads.Length == 0)
        {
            lines.Add(new SetupCheckLine(
                SetupCheckLine.Note,
                $"{managerLabel} does not say where {library.Name}'s downloads arrive. Its hand-offs have to sit inside this library's watched folder."));
        }
        else if (watched.Length > 0 && Inside(downloads, watched))
        {
            lines.Add(new SetupCheckLine(
                SetupCheckLine.Ok,
                $"{library.Name}'s downloads arrive in {downloads}, inside the watched folder, so Weir accepts its hand-offs."));
        }
        else
        {
            lines.Add(new SetupCheckLine(
                SetupCheckLine.Problem,
                $"{library.Name}'s downloads arrive in {downloads}, which is not inside the watched folder, so Weir would refuse its hand-offs. " +
                $"Use {managerLabel}'s folders."));
        }

        var processed = PyStrings.Strip(library.OutputPath ?? string.Empty);
        var output = PyStrings.Strip(outputFolder ?? string.Empty);
        if (processed.Length > 0)
        {
            lines.Add(output.Length > 0 && Inside(processed, output) && Inside(output, processed)
                ? new SetupCheckLine(SetupCheckLine.Ok, $"{managerLabel} picks up cleaned files from {processed}, the folder this library writes to.")
                : new SetupCheckLine(
                    SetupCheckLine.Problem,
                    $"{managerLabel} picks up cleaned files from {processed}, but this library writes to {(output.Length > 0 ? output : "no output folder")}. " +
                    "Unless both are the same folder seen from two machines, use the same folder."));
        }

        return new DelunoSetupResult(downloads.Length > 0 ? downloads : null, processed.Length > 0 ? processed : null, lines);
    }

    /// <summary><paramref name="path"/> is <paramref name="folder"/> or inside it: case- and separator-insensitive, as <c>HandoffPaths</c> compares.</summary>
    private static bool Inside(string path, string folder)
    {
        var target = Comparable(path);
        var root = Comparable(folder);
        return root.Length > 0 && (target == root || target.StartsWith(root + "/", StringComparison.Ordinal));
    }

    private static string Comparable(string path) => PyStrings.Strip(path.Replace('\\', '/')).TrimEnd('/').ToLowerInvariant();

    private static string Quoted(List<string> hosts) =>
        string.Join(" or ", hosts.Select(host => string.Create(CultureInfo.InvariantCulture, $"\"{host}\"")));
}
