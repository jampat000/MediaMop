using Microsoft.Data.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>The folder columns of one <c>refiner_libraries</c> row.</summary>
public sealed record RefinerLibraryFolderRow(long Id, string MediaType, int DisplayOrder, string WorkFolder, string OutputFolder);

/// <summary>
/// Reads library folders and resolves a library's work folder (ports of <c>list_libraries</c>,
/// <c>resolve_library</c> and <c>effective_library_work_folder</c>).
/// </summary>
public static class RefinerLibraryFolders
{
    private const string LegacyWindowsMovieWork = @"C:\ProgramData\Media\refiner-movie-work";
    private const string LegacyWindowsTvWork = @"C:\ProgramData\Weir\refiner-tv-work";

    /// <summary>Every library, ordered by <c>display_order</c> then <c>id</c>.</summary>
    public static List<RefinerLibraryFolderRow> List(SqliteConnection connection, SqliteTransaction? transaction)
    {
        ArgumentNullException.ThrowIfNull(connection);
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText =
            "SELECT id, media_type, display_order, work_folder, output_folder FROM refiner_libraries ORDER BY display_order, id";
        using var reader = command.ExecuteReader();
        var rows = new List<RefinerLibraryFolderRow>();
        while (reader.Read())
        {
            rows.Add(new RefinerLibraryFolderRow(
                reader.GetInt64(0),
                reader.IsDBNull(1) ? "movie" : reader.GetString(1),
                reader.IsDBNull(2) ? 0 : (int)reader.GetInt64(2),
                reader.IsDBNull(3) ? string.Empty : reader.GetString(3),
                reader.IsDBNull(4) ? string.Empty : reader.GetString(4)));
        }

        return rows;
    }

    /// <summary><c>normalize_media_scope</c>.</summary>
    public static string NormalizeMediaScope(string? raw) =>
        string.Equals((string.IsNullOrEmpty(raw) ? "movie" : raw).Trim(), "tv", StringComparison.OrdinalIgnoreCase) ? "tv" : "movie";

    /// <summary><c>resolve_library</c>: by id when the payload has one, else the seeded (oldest) library for the scope.</summary>
    public static RefinerLibraryFolderRow? Resolve(IReadOnlyList<RefinerLibraryFolderRow> libraries, long? libraryId, string? mediaScope)
    {
        ArgumentNullException.ThrowIfNull(libraries);
        if (libraryId is { } id && libraries.FirstOrDefault(library => library.Id == id) is { } found)
        {
            return found;
        }

        var scope = NormalizeMediaScope(mediaScope);
        return libraries.FirstOrDefault(library => library.MediaType == scope);
    }

    public static string DefaultMovieWorkFolder(string weirHome) => Path.Join(Path.GetFullPath(weirHome), "refiner", "refiner-movie-work");

    public static string DefaultTvWorkFolder(string weirHome) => Path.Join(Path.GetFullPath(weirHome), "refiner", "refiner-tv-work");

    /// <summary><c>effective_library_work_folder</c>: the library's own folder, or the per-scope default it used to use.</summary>
    public static string EffectiveWorkFolder(RefinerLibraryFolderRow library, string weirHome)
    {
        ArgumentNullException.ThrowIfNull(library);
        var raw = library.WorkFolder.Trim();
        var scope = (string.IsNullOrEmpty(library.MediaType) ? "movie" : library.MediaType).Trim().ToLowerInvariant();
        if (raw.Length == 0 || IsLegacyDefaultWorkFolder(raw, scope))
        {
            return scope == "tv" ? DefaultTvWorkFolder(weirHome) : DefaultMovieWorkFolder(weirHome);
        }

        return raw;
    }

    /// <summary><c>Path(text).expanduser()</c> made absolute, for touching the filesystem.</summary>
    public static string ExpandForFilesystem(string path)
    {
        ArgumentNullException.ThrowIfNull(path);
        var text = path;
        if (text == "~" || text.StartsWith("~/", StringComparison.Ordinal) || text.StartsWith("~\\", StringComparison.Ordinal))
        {
            text = Path.Join(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), text.Length > 1 ? text[2..] : string.Empty);
        }

        return Path.GetFullPath(text);
    }

    private static bool IsLegacyDefaultWorkFolder(string raw, string scope)
    {
        var legacy = scope == "tv" ? LegacyWindowsTvWork : LegacyWindowsMovieWork;
        return string.Equals(raw.TrimEnd('\\', '/'), legacy.TrimEnd('\\', '/'), StringComparison.OrdinalIgnoreCase);
    }
}
