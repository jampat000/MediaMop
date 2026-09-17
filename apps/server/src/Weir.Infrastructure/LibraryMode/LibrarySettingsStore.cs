using Weir.Core.LibraryMode;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>
/// Per-library #505 settings (<see cref="LibrarySettings"/>): real columns on <c>refiner_libraries</c>
/// (<c>library_schedule_enabled</c>, <c>clean_hardlinked_files</c>, <c>skip_if_manager_would_redownload</c>)
/// plus the <c>library_folders</c> table, since #557's migration (0038_library_mode_settings) moved this off
/// the one permanent <c>refiner_jobs</c> row per library that job-row retention could otherwise prune.
/// </summary>
public static class LibrarySettingsStore
{
    /// <summary>Every library folder configured on any library, de-duplicated — for the #506 startup sweep's folder-walk fallback.</summary>
    public static async Task<IReadOnlyList<string>> AllFoldersAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var rows = await uow.QueryAsync(
            "SELECT DISTINCT folder FROM library_folders",
            reader => reader.GetString(0)).ConfigureAwait(false);
        return rows.Distinct(StringComparer.Ordinal).ToList();
    }

    public static async Task<LibrarySettings> GetAsync(UnitOfWork uow, long libraryId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var rows = await uow.QueryAsync(
            "SELECT library_schedule_enabled, clean_hardlinked_files, skip_if_manager_would_redownload FROM refiner_libraries WHERE id = @id",
            reader => (
                ScheduleEnabled: SqliteValues.GetBool(reader, 0),
                CleanHardlinkedFiles: SqliteValues.GetBool(reader, 1),
                SkipIfManagerWouldRedownload: SqliteValues.GetBool(reader, 2)),
            ("@id", libraryId)).ConfigureAwait(false);
        if (rows.Count == 0)
        {
            return LibrarySettings.Empty;
        }

        var row = rows[0];
        var folders = await FoldersForAsync(uow, libraryId).ConfigureAwait(false);
        return new LibrarySettings(folders, row.ScheduleEnabled, row.CleanHardlinkedFiles, row.SkipIfManagerWouldRedownload);
    }

    public static async Task SetAsync(UnitOfWork uow, long libraryId, LibrarySettings settings)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(settings);
        await uow.ExecuteAsync(
            "UPDATE refiner_libraries SET library_schedule_enabled = @schedule, clean_hardlinked_files = @clean_hardlinked, " +
            "skip_if_manager_would_redownload = @skip_redownload, updated_at = CURRENT_TIMESTAMP WHERE id = @id",
            ("@schedule", settings.ScheduleEnabled ? 1 : 0),
            ("@clean_hardlinked", settings.CleanHardlinkedFiles ? 1 : 0),
            ("@skip_redownload", settings.SkipIfManagerWouldRedownload ? 1 : 0),
            ("@id", libraryId)).ConfigureAwait(false);

        await uow.ExecuteAsync("DELETE FROM library_folders WHERE library_id = @id", ("@id", libraryId)).ConfigureAwait(false);
        for (var position = 0; position < settings.Folders.Count; position++)
        {
            await uow.ExecuteAsync(
                "INSERT INTO library_folders (library_id, folder, position) VALUES (@id, @folder, @position)",
                ("@id", libraryId), ("@folder", settings.Folders[position]), ("@position", position)).ConfigureAwait(false);
        }
    }

    /// <summary>Removes a library's scan-history rows (the library itself is being deleted; its settings and folder
    /// rows go with it automatically — <c>library_folders</c>/<c>library_files</c> both cascade from <c>refiner_libraries</c>).</summary>
    public static async Task DeleteAllForLibraryAsync(UnitOfWork uow, long libraryId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        await uow.ExecuteAsync(
            "DELETE FROM refiner_jobs WHERE job_kind = @scanKind AND dedupe_key LIKE @prefix ESCAPE '\\'",
            ("@scanKind", LibraryModeJobKinds.ScanKind),
            ("@prefix", EscapeLike(LibraryModeJobKinds.ScanDedupeKeyPrefix(libraryId)) + "%")).ConfigureAwait(false);
        await uow.ExecuteAsync(
            "DELETE FROM refiner_jobs WHERE job_kind = @cleanKind AND dedupe_key LIKE @prefix ESCAPE '\\'",
            ("@cleanKind", LibraryModeJobKinds.CleanKind),
            ("@prefix", EscapeLike($"{LibraryModeJobKinds.CleanKind}:{libraryId}:") + "%")).ConfigureAwait(false);
    }

    private static async Task<List<string>> FoldersForAsync(UnitOfWork uow, long libraryId) =>
        await uow.QueryAsync(
            "SELECT folder FROM library_folders WHERE library_id = @id ORDER BY position, id",
            reader => reader.GetString(0),
            ("@id", libraryId)).ConfigureAwait(false);

    private static string EscapeLike(string value) =>
        value.Replace("\\", "\\\\", StringComparison.Ordinal).Replace("%", "\\%", StringComparison.Ordinal).Replace("_", "\\_", StringComparison.Ordinal);
}
