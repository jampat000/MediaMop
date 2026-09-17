using System.Collections.Concurrent;
using Weir.Core.Json;
using Weir.Core.Library;
using Weir.Core.MediaManagers;
using Weir.Core.Rules;
using Weir.Core.Time;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Library;

/// <summary>
/// In-memory <see cref="IRemovedTrackStore"/> (#509 step 1): keeps the most recently recorded removed
/// tracks for each file for the life of the process. This is the store registered by default — nothing in
/// this build yet needs the records to outlive a restart, since the library-mode job that would call
/// <see cref="RecordAsync"/> for real (#505) has not landed. Safe as a DI singleton.
/// </summary>
public sealed class InMemoryRemovedTrackStore : IRemovedTrackStore
{
    private readonly ConcurrentDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>> _byFile = new();

    public Task RecordAsync(RemovedTrackFileKey key, IReadOnlyList<RemovedTrackRecord> tracks, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(tracks);
        _byFile[key] = [.. tracks];
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<RemovedTrackRecord>> GetAsync(RemovedTrackFileKey key, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        return Task.FromResult(_byFile.TryGetValue(key, out var tracks) ? tracks : (IReadOnlyList<RemovedTrackRecord>)[]);
    }

    public Task<IReadOnlyDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>> GetAllAsync(CancellationToken cancellationToken = default) =>
        Task.FromResult<IReadOnlyDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>>(
            new Dictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>(_byFile));
}

/// <summary>
/// The payload-backed alternative (#509 step 1's other option): <c>refiner_file_logs.detail_json</c> is an
/// existing JSON-capable column ("free-form JSON" per <c>refiner_file_log_model.py</c>) that a completed
/// Refiner pass already writes plan detail into on the Python side (<c>removed_audio</c>/<c>removed_subtitles</c>
/// among other keys — see <c>apps/backend/tests/test_refiner_file_remux_pass_run.py::test_live_result_keeps_removed_track_lists_for_activity_detail</c>).
/// Reusing it needs no migration, honouring the schema freeze until #523 (ADR-0017).
///
/// <para><b>What this class actually does today.</b> The .NET remux-pass job handler that would write a
/// real <c>refiner_file_logs</c> row is not ported yet (<c>Weir.Infrastructure.Refiner.FileLogStore</c> only
/// has read and prune methods — see <c>apps/server/README.md</c>'s "unported job kinds" note). So that this
/// store is genuinely usable — not just a read-only stub waiting on other work — <see cref="RecordAsync"/>
/// writes its own <c>refiner_file_logs</c> row (<c>outcome = "library.removed_tracks"</c>) holding a
/// structured <c>removed_track_records</c> array under <c>detail_json</c>. <see cref="GetAsync"/> reads the
/// newest row for the file back and prefers that structured array; when a row instead only has the legacy
/// <c>removed_audio</c>/<c>removed_subtitles</c> string arrays (written by a real pass once #505/#523 land,
/// or by the Python backend), it best-effort parses those into <see cref="RemovedTrackRecord"/>s with
/// <c>Codec = "unknown"</c> and the whole sentence kept as <see cref="RemovedTrackRecord.Reason"/> — good
/// enough for the diff service, not a substitute for a pass recording the structured shape directly once it
/// can (a follow-up to have the remux pass job itself populate <c>removed_track_records</c> is expected once
/// it is ported, at which point <see cref="RecordAsync"/> here becomes unnecessary).</para>
/// </summary>
public sealed class FileLogRemovedTrackStore : IRemovedTrackStore
{
    private const string DetailKey = "removed_track_records";
    private const string Outcome = "library.removed_tracks";

    private readonly SqliteDatabase _database;
    private readonly TimeProvider _time;

    public FileLogRemovedTrackStore(SqliteDatabase database, TimeProvider? time = null)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _time = time ?? TimeProvider.System;
    }

    public async Task RecordAsync(RemovedTrackFileKey key, IReadOnlyList<RemovedTrackRecord> tracks, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(tracks);
        var detail = new PyDict().Set(DetailKey, new PyList(tracks.Select(ToJson)));
        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        await uow.ExecuteAsync(
            "INSERT INTO refiner_file_logs (library_id, relative_path, library_name, outcome, title, detail_json, recorded_at) " +
            "VALUES (@library_id, @relative_path, '', @outcome, @relative_path, @detail_json, @recorded_at)",
            ("@library_id", key.LibraryId),
            ("@relative_path", key.RelativePath),
            ("@outcome", Outcome),
            ("@detail_json", PyJsonWriter.Dumps(detail, PyJsonFormat.Compact)),
            ("@recorded_at", SqliteValues.ToSqlite(PyDateTime.FromUtc(_time.GetUtcNow().UtcDateTime)))).ConfigureAwait(false);
        await uow.CommitAsync().ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<RemovedTrackRecord>> GetAsync(RemovedTrackFileKey key, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(key);
        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        var detailJson = await uow.ScalarAsync(
            "SELECT detail_json FROM refiner_file_logs WHERE relative_path = @relative_path AND library_id IS @library_id " +
            "ORDER BY recorded_at DESC, id DESC LIMIT 1",
            ("@relative_path", key.RelativePath),
            ("@library_id", key.LibraryId)).ConfigureAwait(false);
        return detailJson is string json ? FromDetail(json) : [];
    }

    public async Task<IReadOnlyDictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>> GetAllAsync(CancellationToken cancellationToken = default)
    {
        await using var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
        var rows = await uow.QueryAsync(
            "SELECT library_id, relative_path, detail_json FROM (" +
            "  SELECT library_id, relative_path, detail_json, " +
            "         ROW_NUMBER() OVER (PARTITION BY library_id, relative_path ORDER BY recorded_at DESC, id DESC) AS rn " +
            "  FROM refiner_file_logs" +
            ") WHERE rn = 1",
            reader => (
                LibraryId: reader.IsDBNull(0) ? (long?)null : reader.GetInt64(0),
                RelativePath: SqliteValues.GetString(reader, 1),
                DetailJson: SqliteValues.GetString(reader, 2))).ConfigureAwait(false);

        var result = new Dictionary<RemovedTrackFileKey, IReadOnlyList<RemovedTrackRecord>>();
        foreach (var row in rows)
        {
            var tracks = FromDetail(row.DetailJson);
            if (tracks.Count > 0)
            {
                result[new RemovedTrackFileKey(row.LibraryId, row.RelativePath)] = tracks;
            }
        }

        return result;
    }

    private static List<RemovedTrackRecord> FromDetail(string detailJson)
    {
        var detail = FileLogStore.ParseDetail(detailJson);
        if (detail.Get(DetailKey) is PyList structured)
        {
            return [.. structured.Items.OfType<PyDict>().Select(FromJson)];
        }

        // Legacy fallback: a row written before the structured shape existed (or by the Python backend)
        // only has these free-text lists. Best-effort only — see the type's remarks.
        var records = new List<RemovedTrackRecord>();
        AddLegacy(records, detail.Get("removed_audio"), RemovedTrackType.Audio);
        AddLegacy(records, detail.Get("removed_subtitles"), RemovedTrackType.Subtitle);
        return records;
    }

    private static void AddLegacy(List<RemovedTrackRecord> records, PyJson? value, RemovedTrackType type)
    {
        if (value is not PyList list)
        {
            return;
        }

        foreach (var item in list.Items.OfType<PyStr>())
        {
            var text = item.Value;
            // "jpn: removed (not selected — ...)" and "eng (commentary excluded — ...)" both
            // lead with the language; the non-selected shape adds a trailing colon before the space.
            var lang = text.Split(' ', 2)[0].TrimEnd(':');
            records.Add(new RemovedTrackRecord
            {
                Language = lang.Length > 0 ? lang : "und",
                Type = type,
                Codec = "unknown",
                Reason = text,
            });
        }
    }

    private static PyJson ToJson(RemovedTrackRecord record) => new PyDict()
        .Set("language", record.Language)
        .Set("type", record.Type == RemovedTrackType.Audio ? "audio" : "subtitle")
        .Set("codec", record.Codec)
        .Set("variant", record.Variant)
        .Set("reason", record.Reason);

    private static RemovedTrackRecord FromJson(PyDict dict) => new()
    {
        Language = PyValues.Text(dict.Get("language")) ?? "und",
        Type = PyValues.Text(dict.Get("type")) == "subtitle" ? RemovedTrackType.Subtitle : RemovedTrackType.Audio,
        Codec = PyValues.Text(dict.Get("codec")) ?? "unknown",
        Variant = PyValues.Text(dict.Get("variant")),
        Reason = PyValues.Text(dict.Get("reason")) ?? string.Empty,
    };
}
