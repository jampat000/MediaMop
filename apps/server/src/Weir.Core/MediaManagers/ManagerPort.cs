using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>The kinds, lanes and scopes a media manager connection can have.</summary>
public static class MediaManagerKinds
{
    /// <summary><c>MEDIA_MANAGER_KINDS</c>.</summary>
    public static readonly IReadOnlyList<string> All = ["radarr", "sonarr", "deluno", "native"];

    /// <summary><c>SEARCH_LANES</c>.</summary>
    public static readonly IReadOnlyList<string> SearchLanes = ["missing", "upgrade"];

    public const string Movie = "movie";
    public const string Tv = "tv";

    /// <summary><c>ALL_MEDIA_SCOPES</c>.</summary>
    public static readonly IReadOnlySet<string> AllMediaScopes = new SortedSet<string>(StringComparer.Ordinal) { Movie, Tv };

    private static readonly Dictionary<string, string> KindLabels = new(StringComparer.Ordinal)
    {
        ["radarr"] = "Radarr",
        ["sonarr"] = "Sonarr",
        ["deluno"] = "Deluno",
        ["native"] = "Media manager",
    };

    /// <summary><c>label_for_connection</c>: <c>"Deluno (Main)"</c>; a connection named after its product is not repeated.</summary>
    public static string LabelForConnection(string? kind, string? name)
    {
        var product = KindLabels.GetValueOrDefault(PyStrings.Strip(kind ?? string.Empty).ToLowerInvariant(), "Media manager");
        var label = PyStrings.Strip(name ?? string.Empty);
        if (label.Length == 0)
        {
            return product;
        }

        return string.Equals(label.ToUpperInvariant().ToLowerInvariant(), product.ToUpperInvariant().ToLowerInvariant(), StringComparison.Ordinal)
            ? label
            : $"{product} ({label})";
    }
}

/// <summary>The three answers a manager can give (<c>SignalStatus</c>).</summary>
public static class SignalStatus
{
    public const string Reported = "reported";
    public const string NoSignal = "no_signal";
    public const string Unreachable = "unreachable";
}

/// <summary>One configured manager, resolved far enough to talk to. <see cref="ConnectionId"/> is null for the environment credentials.</summary>
public sealed record ManagerConnection(string Kind, string Name, string BaseUrl, string ApiKey, long? ConnectionId = null)
{
    public string Label => MediaManagerKinds.LabelForConnection(Kind, Name);
}

/// <summary>One in-progress item, tagged with the scope whose dialect can read it.</summary>
public sealed record ManagerQueueRow(string Scope, PyDict Payload);

/// <summary>What one manager said when asked whether it is mid-import. Only reported-and-empty means clear.</summary>
public sealed record ManagerQueueSignal(ManagerConnection Connection, string Status, IReadOnlyList<ManagerQueueRow> Rows, string? Detail = null)
{
    public bool IsReported => Status == SignalStatus.Reported;
}

/// <summary>Library files one manager still keeps. Only reported-and-empty clears a delete.</summary>
public sealed record ManagerLibraryTruth(ManagerConnection Connection, string Status, IReadOnlyList<string> LibraryFilePaths, string? Detail = null)
{
    public bool IsReported => Status == SignalStatus.Reported;
}

/// <summary>One file a manager's library holds, matched to the title that owns it (<c>list_library_files</c>, #507).</summary>
public sealed record ManagerLibraryFile(string TitleId, string TitleName, string FilePath);

/// <summary>Every library file one manager reports for a scope, matched to titles, or why it could not (#507).</summary>
public sealed record ManagerLibraryFilesSignal(ManagerConnection Connection, string Status, IReadOnlyList<ManagerLibraryFile> Files, string? Detail = null)
{
    public bool IsReported => Status == SignalStatus.Reported;
}

/// <summary>What happened when a manager was asked to re-read a changed file (<c>file_changed</c>, #507).</summary>
public enum ManagerNotifyOutcome
{
    /// <summary>The manager accepted the call.</summary>
    Notified,

    /// <summary>This manager does not offer the signal at all (Deluno without the manifest capability) — no call was made.</summary>
    NotSupported,
}

/// <summary>What a kind of manager can be asked, before anyone talks to it.</summary>
public sealed record ManagerCapabilities(IReadOnlySet<string> Scopes, bool ReportsQueue, bool ReportsLibraryTruth, string Summary, bool RemovesQueueItems = false);

/// <summary>One library a manager says it looks after. <see cref="RootPath"/> is a path on the manager's host.</summary>
public sealed record ManagerLibraryDescriptor(
    string Key,
    string Name,
    string? MediaScope,
    string? RootPath = null,
    string? OutputPath = null,
    bool ProcessesBeforeImport = false);

/// <summary>A live answer to "what do you manage", degrading to the static capabilities.</summary>
public sealed record ManagerDescription(
    ManagerConnection Connection,
    string Status,
    ManagerCapabilities Capabilities,
    IReadOnlyList<string> LibraryRoots,
    IReadOnlyList<ManagerLibraryDescriptor> Libraries,
    string? Detail = null,
    IReadOnlySet<string>? AdvertisedCapabilities = null);

/// <summary>A call to a manager failed (<c>MediaManagerHttpError</c>).</summary>
public class MediaManagerHttpException : Exception
{
    public MediaManagerHttpException()
    {
    }

    public MediaManagerHttpException(string message)
        : base(message)
    {
    }

    public MediaManagerHttpException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>The manager answered 429 (<c>MediaManagerRateLimitedError</c>). Back off; never retry inside the call.</summary>
public sealed class MediaManagerRateLimitedException : MediaManagerHttpException
{
    public MediaManagerRateLimitedException()
    {
    }

    public MediaManagerRateLimitedException(string message)
        : base(message)
    {
    }

    public MediaManagerRateLimitedException(string message, Exception innerException)
        : base(message, innerException)
    {
    }

    public MediaManagerRateLimitedException(string message, double? retryAfterSeconds)
        : base(message)
    {
        RetryAfterSeconds = retryAfterSeconds;
    }

    public double? RetryAfterSeconds { get; }
}

/// <summary>The manager could not be reached at all: Python's <c>OSError</c> (refused, timed out, name not resolved).</summary>
public sealed class MediaManagerUnreachableException : Exception
{
    public MediaManagerUnreachableException()
    {
    }

    public MediaManagerUnreachableException(string message)
        : base(message)
    {
    }

    public MediaManagerUnreachableException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>One kind of manager answering the three questions (<c>MediaManagerPort</c>).</summary>
public interface IMediaManagerPort
{
    string Kind { get; }

    /// <summary>What this kind can be asked. No network.</summary>
    ManagerCapabilities Capabilities();

    Task<ManagerDescription> DescribeAsync(ManagerConnection connection, CancellationToken cancellationToken = default);

    Task<ManagerQueueSignal> QueueRowsAsync(ManagerConnection connection, CancellationToken cancellationToken = default);

    /// <summary>Remove one queue item and blocklist its release. Throws <see cref="MediaManagerHttpException"/> when refused.</summary>
    Task RemoveQueueItemAsync(ManagerConnection connection, PyDict row, CancellationToken cancellationToken = default);

    Task<ManagerLibraryTruth> LibraryTruthAsync(ManagerConnection connection, string mediaScope, CancellationToken cancellationToken = default);

    /// <summary>
    /// Every library file this manager knows for <paramref name="mediaScope"/>, matched to its title
    /// (<c>list_library_files</c>, #507). <see cref="SignalStatus.NoSignal"/> for a manager with no
    /// per-file listing (Deluno's external API offers none); no network is spent finding that out.
    /// </summary>
    Task<ManagerLibraryFilesSignal> ListLibraryFilesAsync(ManagerConnection connection, string mediaScope, CancellationToken cancellationToken = default);

    /// <summary>
    /// Tell this manager one of its files changed on disk, so it re-reads it (<c>file_changed</c>, #507).
    /// <paramref name="advertisedCapabilities"/> is the manifest capability set from a prior
    /// <see cref="DescribeAsync"/> (avoids a second round trip just to check it); <paramref name="titleId"/>
    /// is required for an arr manager (the id <see cref="ListLibraryFilesAsync"/> matched) and ignored by an
    /// external one, which matches by <paramref name="filePath"/> itself. Throws
    /// <see cref="MediaManagerHttpException"/> or <see cref="MediaManagerUnreachableException"/> when the
    /// call was attempted and failed; returns <see cref="ManagerNotifyOutcome.NotSupported"/> without any
    /// network call when this manager cannot be asked at all.
    /// </summary>
    Task<ManagerNotifyOutcome> FileChangedAsync(
        ManagerConnection connection,
        IReadOnlySet<string> advertisedCapabilities,
        string? titleId,
        string filePath,
        string? reason,
        CancellationToken cancellationToken = default);
}
