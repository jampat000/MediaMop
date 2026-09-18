using Microsoft.Data.Sqlite;

namespace Weir.Infrastructure.Jobs;

/// <summary>The folder columns of one <c>libraries</c> row.</summary>
public sealed record ProcessingLibraryFolderRow(long Id, string MediaType, int DisplayOrder, string WorkFolder, string OutputFolder);

/// <summary>
/// Reads library folders and resolves a library's work folder (ports of <c>list_libraries</c>,
/// <c>resolve_library</c> and <c>effective_library_work_folder</c>).
/// </summary>
public static class ProcessingLibraryFolders
{
    /// <summary>Every library, ordered by <c>display_order</c> then <c>id</c>.</summary>
    public static List<ProcessingLibraryFolderRow> List(SqliteConnection connection, SqliteTransaction? transaction)
    {
        ArgumentNullException.ThrowIfNull(connection);
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText =
            "SELECT id, media_type, display_order, work_folder, output_folder FROM libraries ORDER BY display_order, id";
        using var reader = command.ExecuteReader();
        var rows = new List<ProcessingLibraryFolderRow>();
        while (reader.Read())
        {
            rows.Add(new ProcessingLibraryFolderRow(
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
    public static ProcessingLibraryFolderRow? Resolve(IReadOnlyList<ProcessingLibraryFolderRow> libraries, long? libraryId, string? mediaScope)
    {
        ArgumentNullException.ThrowIfNull(libraries);
        if (libraryId is { } id && libraries.FirstOrDefault(library => library.Id == id) is { } found)
        {
            return found;
        }

        var scope = NormalizeMediaScope(mediaScope);
        return libraries.FirstOrDefault(library => library.MediaType == scope);
    }

    public static string DefaultMovieWorkFolder(string weirHome) => Path.Join(Path.GetFullPath(weirHome), "processing", "processing-movie-work");

    public static string DefaultTvWorkFolder(string weirHome) => Path.Join(Path.GetFullPath(weirHome), "processing", "processing-tv-work");

    /// <summary>
    /// <c>effective_library_work_folder</c>: the library's own folder, or the per-scope default when it
    /// has none.
    /// </summary>
    /// <remarks>
    /// Until 3.0.0 this also treated two hard-coded Windows paths — <c>C:\ProgramData\Media\
    /// processing-movie-work</c> and <c>C:\ProgramData\Weir\processing-tv-work</c>, the defaults an
    /// older MediaMop-era install wrote into <c>work_folder</c> — as if the column were empty, so they
    /// silently resolved to the <c>WEIR_HOME</c> default instead. Those are gone. A row still holding
    /// one of those paths is now taken at face value, like any other custom path: it is used as
    /// written, and if the folder does not exist the caller refuses the run with "the library's
    /// work/temp folder must be an existing directory when set to a custom path" rather than quietly
    /// working somewhere else. An empty <c>work_folder</c> is untouched and still gets the default.
    /// </remarks>
    public static string EffectiveWorkFolder(ProcessingLibraryFolderRow library, string weirHome)
    {
        ArgumentNullException.ThrowIfNull(library);
        var raw = library.WorkFolder.Trim();
        if (raw.Length > 0)
        {
            return raw;
        }

        var scope = (string.IsNullOrEmpty(library.MediaType) ? "movie" : library.MediaType).Trim().ToLowerInvariant();
        return scope == "tv" ? DefaultTvWorkFolder(weirHome) : DefaultMovieWorkFolder(weirHome);
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
}
