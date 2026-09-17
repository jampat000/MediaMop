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
}
