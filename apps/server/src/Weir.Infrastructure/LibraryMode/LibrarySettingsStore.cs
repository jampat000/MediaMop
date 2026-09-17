using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>
/// Per-library #505 settings (<see cref="LibrarySettings"/>), kept on a single, permanent <c>refiner_jobs</c> row rather than a
/// new table or column (ADR-0017 freezes the schema until #523 — see <c>apps/server/README.md</c>, "Library mode"). The row's
/// <c>job_kind</c> is <see cref="LibraryModeJobKinds.SettingsKind"/>, its status is always <c>completed</c> so no worker ever
/// claims it, and it is written with a plain <c>INSERT ... ON CONFLICT DO UPDATE</c> rather than through
/// <see cref="RefinerJobStore"/>'s enqueue path, which always inserts a fresh <c>pending</c> row.
/// </summary>
public static class LibrarySettingsStore
{
    /// <summary>Every library folder configured on any library, de-duplicated — for the #506 startup sweep's folder-walk fallback.</summary>
    public static async Task<IReadOnlyList<string>> AllFoldersAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var rows = await uow.QueryAsync(
            "SELECT payload_json FROM refiner_jobs WHERE job_kind = @kind",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0),
            ("@kind", LibraryModeJobKinds.SettingsKind)).ConfigureAwait(false);
        var folders = new List<string>();
        foreach (var json in rows)
        {
            if (string.IsNullOrWhiteSpace(json))
            {
                continue;
            }

            try
            {
                folders.AddRange(LibrarySettings.FromPayload(PyJsonParser.Parse(json) as PyDict).Folders);
            }
            catch (PyJsonDecodeException)
            {
            }
        }

        return folders.Distinct(StringComparer.Ordinal).ToList();
    }

    public static async Task<LibrarySettings> GetAsync(UnitOfWork uow, long libraryId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var payloadJson = await uow.ScalarAsync(
            "SELECT payload_json FROM refiner_jobs WHERE dedupe_key = @key",
            ("@key", LibraryModeJobKinds.SettingsDedupeKey(libraryId))).ConfigureAwait(false);
        if (payloadJson is not string json || string.IsNullOrWhiteSpace(json))
        {
            return LibrarySettings.Empty;
        }

        try
        {
            return LibrarySettings.FromPayload(PyJsonParser.Parse(json) as PyDict);
        }
        catch (PyJsonDecodeException)
        {
            return LibrarySettings.Empty;
        }
    }

    public static async Task SetAsync(UnitOfWork uow, long libraryId, LibrarySettings settings)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(settings);
        var json = PyJsonWriter.Dumps(settings.ToPayload(libraryId), PyJsonFormat.Compact);
        await uow.ExecuteAsync(
            """
            INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, max_attempts, runner_cost, priority)
            VALUES (@key, @kind, @payload, @status, 1, 0, 0)
            ON CONFLICT(dedupe_key) DO UPDATE SET payload_json = excluded.payload_json, updated_at = CURRENT_TIMESTAMP
            """,
            ("@key", LibraryModeJobKinds.SettingsDedupeKey(libraryId)),
            ("@kind", LibraryModeJobKinds.SettingsKind),
            ("@payload", json),
            ("@status", RefinerJobStatus.Completed)).ConfigureAwait(false);
    }

    /// <summary>Removes a library's settings and scan-history rows (the library itself is being deleted).</summary>
    public static async Task DeleteAllForLibraryAsync(UnitOfWork uow, long libraryId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        await uow.ExecuteAsync(
            "DELETE FROM refiner_jobs WHERE dedupe_key = @key",
            ("@key", LibraryModeJobKinds.SettingsDedupeKey(libraryId))).ConfigureAwait(false);
        await uow.ExecuteAsync(
            "DELETE FROM refiner_jobs WHERE job_kind = @scanKind AND dedupe_key LIKE @prefix ESCAPE '\\'",
            ("@scanKind", LibraryModeJobKinds.ScanKind),
            ("@prefix", EscapeLike(LibraryModeJobKinds.ScanDedupeKeyPrefix(libraryId)) + "%")).ConfigureAwait(false);
        await uow.ExecuteAsync(
            "DELETE FROM refiner_jobs WHERE job_kind = @cleanKind AND dedupe_key LIKE @prefix ESCAPE '\\'",
            ("@cleanKind", LibraryModeJobKinds.CleanKind),
            ("@prefix", EscapeLike($"{LibraryModeJobKinds.CleanKind}:{libraryId}:") + "%")).ConfigureAwait(false);
    }

    private static string EscapeLike(string value) =>
        value.Replace("\\", "\\\\", StringComparison.Ordinal).Replace("%", "\\%", StringComparison.Ordinal).Replace("_", "\\_", StringComparison.Ordinal);
}
