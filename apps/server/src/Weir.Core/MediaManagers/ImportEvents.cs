using System.Numerics;
using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>
/// A file a media manager wants Weir to act on (port of <c>import_events.MediaManagerImportEvent</c>).
/// <c>imported</c> is accepted and ignored; <c>handoff</c> is Refiner's cue and the only kind with a callback.
/// </summary>
public sealed record MediaManagerImportEvent
{
    public const string Imported = "imported";
    public const string Handoff = "handoff";

    public required string SourceKey { get; init; }
    public required string EventKind { get; init; }
    public required string MediaScope { get; init; }
    public required string FilePath { get; init; }
    public string? Title { get; init; }
    public BigInteger? Year { get; init; }
    public string? ShowTitle { get; init; }
    public BigInteger? SeasonNumber { get; init; }
    public BigInteger? EpisodeNumber { get; init; }
    public string? EpisodeTitle { get; init; }
    public BigInteger? SourceEntityId { get; init; }
    public string? HandoffId { get; init; }
    public string? CallbackPath { get; init; }
    public string? ReleaseName { get; init; }

    /// <summary>The manager's own library id; Deluno refuses a processor event without it.</summary>
    public string? LibraryId { get; init; }
}

/// <summary>How one manager phrases an inbound event.</summary>
public sealed record MediaManagerDialect(string Key, string DisplayName, Func<PyDict, MediaManagerImportEvent?> Normalize);

/// <summary>The inbound dialects (port of <c>weir.platform.media_managers.import_events</c>).</summary>
public static class ImportEvents
{
    /// <summary><c>MEDIA_MANAGER_DIALECTS</c>, in declaration order.</summary>
    public static IReadOnlyDictionary<string, MediaManagerDialect> Dialects { get; } = new[]
    {
        new MediaManagerDialect("radarr", "Radarr", NormalizeRadarr),
        new MediaManagerDialect("sonarr", "Sonarr", NormalizeSonarr),
        new MediaManagerDialect("deluno", "Deluno", NormalizeDeluno),
        new MediaManagerDialect("native", "Generic (Weir native payload)", NormalizeNative),
    }.ToDictionary(d => d.Key, StringComparer.Ordinal);

    /// <summary><c>dialect_for_source</c>: case- and whitespace-insensitive.</summary>
    public static MediaManagerDialect? DialectForSource(string? sourceKey) =>
        Dialects.GetValueOrDefault(PyStrings.Strip(sourceKey ?? string.Empty).ToLowerInvariant());

    /// <summary><c>known_source_keys</c>: sorted.</summary>
    public static IReadOnlyList<string> KnownSourceKeys() => [.. Dialects.Keys.Order(StringComparer.Ordinal)];

    private static PyDict? Mapping(PyDict body, string key) => body.Get(key) as PyDict;

    private static MediaManagerImportEvent? NormalizeSonarr(PyDict body)
    {
        if (PyValues.Text(body.Get("eventType")) != "Download")
        {
            return null;
        }

        if (body.Get("episodes") is not PyList { Items.Count: > 0 } episodes || episodes.Items[0] is not PyDict episode)
        {
            return null;
        }

        var episodeFile = Mapping(body, "episodeFile");
        var path = episodeFile is null ? null : PyValues.Text(episodeFile.Get("path"));
        if (path is null)
        {
            return null;
        }

        var series = Mapping(body, "series");
        var seriesTitle = series is null ? null : PyValues.Text(series.Get("title"));
        return new MediaManagerImportEvent
        {
            SourceKey = "sonarr",
            EventKind = MediaManagerImportEvent.Imported,
            MediaScope = "tv",
            FilePath = path,
            Title = seriesTitle,
            ShowTitle = seriesTitle,
            SeasonNumber = PyValues.WholeNumber(episode.Get("seasonNumber")),
            EpisodeNumber = PyValues.WholeNumber(episode.Get("episodeNumber")),
            EpisodeTitle = PyValues.Text(episode.Get("title")),
            SourceEntityId = PyValues.WholeNumber(episode.Get("id")),
        };
    }

    private static MediaManagerImportEvent? NormalizeRadarr(PyDict body)
    {
        if (PyValues.Text(body.Get("eventType")) != "Download")
        {
            return null;
        }

        var movie = Mapping(body, "movie");
        if (movie is null)
        {
            return null;
        }

        var movieFile = Mapping(body, "movieFile");
        var path = movieFile is null ? null : PyValues.Text(movieFile.Get("path"));
        if (path is null)
        {
            return null;
        }

        return new MediaManagerImportEvent
        {
            SourceKey = "radarr",
            EventKind = MediaManagerImportEvent.Imported,
            MediaScope = "movie",
            FilePath = path,
            Title = PyValues.Text(movie.Get("title")),
            Year = PyValues.WholeNumber(movie.Get("year")),
            SourceEntityId = PyValues.WholeNumber(movie.Get("id")),
        };
    }

    /// <summary>The inbound <c>_scope_from_media_type</c> (fewer spellings than the outbound one).</summary>
    public static string? ScopeFromMediaType(PyJson? raw)
    {
        var value = (PyValues.Text(raw) ?? string.Empty).ToLowerInvariant();
        return value switch
        {
            "movie" or "movies" or "film" => "movie",
            "tv" or "series" or "show" or "episode" => "tv",
            _ => null,
        };
    }

    private static MediaManagerImportEvent? NormalizeDeluno(PyDict body)
    {
        if (PyValues.Text(body.Get("eventType")) != "deluno.processor-handoff")
        {
            return null;
        }

        var path = PyValues.Text(body.Get("sourcePath"));
        var scope = ScopeFromMediaType(body.Get("mediaType"));
        if (path is null || scope is null)
        {
            return null;
        }

        var releaseName = PyValues.Text(body.Get("releaseName"));
        return new MediaManagerImportEvent
        {
            SourceKey = "deluno",
            EventKind = MediaManagerImportEvent.Handoff,
            MediaScope = scope,
            FilePath = path,
            Title = releaseName,
            ReleaseName = releaseName,
            HandoffId = PyValues.Text(body.Get("handoffId")),
            CallbackPath = PyValues.Text(body.Get("callbackPath")),
            LibraryId = PyValues.Text(body.Get("libraryId")),
        };
    }

    private static MediaManagerImportEvent? NormalizeNative(PyDict body)
    {
        var kind = (PyValues.Text(body.Get("event")) ?? MediaManagerImportEvent.Imported).ToLowerInvariant();
        if (kind is not (MediaManagerImportEvent.Imported or MediaManagerImportEvent.Handoff))
        {
            return null;
        }

        var path = PyValues.Text(body.Get("filePath")) ?? PyValues.Text(body.Get("file_path"));
        var scope = ScopeFromMediaType(PyValues.Or(body.Get("mediaScope"), body.Get("media_scope")));
        if (path is null || scope is null)
        {
            return null;
        }

        PyJson? Either(string camel, string snake) => PyValues.Or(body.Get(camel), body.Get(snake));
        return new MediaManagerImportEvent
        {
            SourceKey = "native",
            EventKind = kind,
            MediaScope = scope,
            FilePath = path,
            Title = PyValues.Text(body.Get("title")),
            Year = PyValues.WholeNumber(body.Get("year")),
            ShowTitle = PyValues.Text(Either("showTitle", "show_title")),
            SeasonNumber = PyValues.WholeNumber(Either("seasonNumber", "season_number")),
            EpisodeNumber = PyValues.WholeNumber(Either("episodeNumber", "episode_number")),
            EpisodeTitle = PyValues.Text(Either("episodeTitle", "episode_title")),
            SourceEntityId = PyValues.WholeNumber(Either("entityId", "entity_id")),
            HandoffId = PyValues.Text(Either("handoffId", "handoff_id")),
            CallbackPath = PyValues.Text(Either("callbackPath", "callback_path")),
            ReleaseName = PyValues.Text(Either("releaseName", "release_name")),
            LibraryId = PyValues.Text(Either("libraryId", "library_id")),
        };
    }
}
