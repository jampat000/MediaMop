using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>How one kind's outbound dialect is shaped: static per kind, so binding costs no requests.</summary>
public sealed record ManagerKindProfile(string Kind, ManagerCapabilities Capabilities, string? ArrScope = null, string? ArrLibraryPath = null, string? ArrFileKey = null)
{
    public bool IsArr => ArrScope is not null;
}

/// <summary>The four kinds' profiles (the <c>_PORTS</c> table of <c>manager_dialects</c>).</summary>
public static class ManagerKindProfiles
{
    private static readonly Dictionary<string, ManagerKindProfile> Profiles = new(StringComparer.Ordinal)
    {
        ["radarr"] = Arr("radarr", MediaManagerKinds.Movie, "/api/v3/movie", "movieFile"),
        ["sonarr"] = Arr("sonarr", MediaManagerKinds.Tv, "/api/v3/episodefile", null),
        ["deluno"] = External("deluno"),
        ["native"] = External("native"),
    };

    /// <summary><c>port_for_kind</c>'s lookup: case- and whitespace-insensitive.</summary>
    public static ManagerKindProfile? ForKind(string? kind) =>
        Profiles.GetValueOrDefault(PyStrings.Strip(kind ?? string.Empty).ToLowerInvariant());

    /// <summary><c>capabilities_for_kind</c>.</summary>
    public static ManagerCapabilities? CapabilitiesForKind(string? kind) => ForKind(kind)?.Capabilities;

    /// <summary><c>kinds_serving_scope</c>: sorted.</summary>
    public static IReadOnlyList<string> KindsServingScope(string mediaScope) =>
        [.. Profiles.Where(pair => pair.Value.Capabilities.Scopes.Contains(mediaScope)).Select(pair => pair.Key).Order(StringComparer.Ordinal)];

    private static ManagerKindProfile Arr(string kind, string scope, string libraryPath, string? fileKey)
    {
        var scopeWord = scope == MediaManagerKinds.Movie ? "Movies" : "TV episodes";
        var capabilities = new ManagerCapabilities(
            new SortedSet<string>(StringComparer.Ordinal) { scope },
            ReportsQueue: true,
            ReportsLibraryTruth: true,
            $"Looks after {scopeWord}. Weir can ask it what is downloading or importing, and which files it still keeps in its library.",
            RemovesQueueItems: true);
        return new ManagerKindProfile(kind, capabilities, scope, libraryPath, fileKey);
    }

    private static ManagerKindProfile External(string kind) => new(
        kind,
        new ManagerCapabilities(
            MediaManagerKinds.AllMediaScopes,
            ReportsQueue: true,
            ReportsLibraryTruth: false,
            "Looks after Movies and TV episodes. Weir can ask it what is mid-import, but not which files it still keeps, " +
            "so folder cleanup stays off unless another manager can answer that."));
}
