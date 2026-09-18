using Weir.Core.Library;
using Weir.Core.LibraryMode;
using Weir.Core.Rules;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Library;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Sqlite.Migrations;

/// <summary>
/// Issue #557: migrations 0002-0006 each copy data out of the old job-payload/detail_json storage they
/// replace. Every test here builds a database at the frozen baseline (<see cref="SchemaMigrator.BaselineRevision"/>,
/// the pre-#557 head every released Weir could create), writes one row by hand in the exact old format,
/// upgrades the database to head (<see cref="SchemaMigrator.EnsureAtHead"/>'s new in-place upgrade path),
/// and proves the same data reads back identically through the real, current store — not a reimplementation
/// of the migration's own SQL.
/// </summary>
public sealed class Issue557MigrationTests : IDisposable
{
    private readonly TempDirectory _temp = new();
    private readonly SqliteDatabase _database;

    public Issue557MigrationTests()
    {
        _database = new SqliteDatabase(_temp.Join("weir.sqlite3"));
        Assert.Equal(SchemaStartupOutcome.Created, new SchemaMigrator(_database).EnsureAtBaseline());
        // The baseline (like the Alembic head it reproduces) seeds two default libraries and a rule set;
        // this test writes its own with predictable ids instead.
        Execute("DELETE FROM refiner_libraries; DELETE FROM refiner_rule_sets;");
    }

    public void Dispose() => _database.ClearPool();

    private void Execute(string sql, params (string Name, object? Value)[] parameters)
    {
        using var connection = _database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        }

        command.ExecuteNonQuery();
    }

    private object? Scalar(string sql, params (string Name, object? Value)[] parameters)
    {
        using var connection = _database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        }

        return command.ExecuteScalar();
    }

    private void Upgrade() => Assert.Equal(SchemaStartupOutcome.Upgraded, new SchemaMigrator(_database).EnsureAtHead());

    [Fact]
    public async Task Rule_set_extras_envelope_migrates_into_real_columns_and_sorters_is_restored_to_a_plain_array()
    {
        Execute(
            "INSERT INTO refiner_rule_sets (name, subtitle_sorters_json) VALUES ('Old Rules', @json)",
            ("@json",
                """
                {"sorters":[{"field":"forced","value":null,"reversed":false}],"rule_extras_v1":{
                "remove_hearing_impaired_subs":true,"audio_keep_mode":"per_language","subtitle_max_per_language":2,
                "subtitle_quality_strategy":"image_first","standardize_track_names":true,
                "track_name_template":"{language} {codec}",
                "track_name_overrides":{"forced":"F","hearing_impaired":"HI","commentary":"C","audio_description":"AD"},
                "clear_video_track_names":true,"remove_chapters":true}}
                """));
        // A legacy row with no envelope at all (this column's only shape before #495/#497/#498) must be
        // left alone: an upgrade changes nothing for it.
        Execute("INSERT INTO refiner_rule_sets (name, subtitle_sorters_json) VALUES ('Legacy', @json)",
            ("@json", """[{"field":"forced","value":null,"reversed":false}]"""));
        Execute("INSERT INTO refiner_rule_sets (name, subtitle_sorters_json) VALUES ('Blank', '')");

        Upgrade();

        await using var uow = await UnitOfWork.OpenAsync(_database);
        var migrated = await LibraryStore.GetRuleSetByNameAsync(uow, "Old Rules");
        Assert.NotNull(migrated);
        Assert.Equal("""[{"field":"forced","value":null,"reversed":false}]""", migrated!.SubtitleSortersJson);
        Assert.True(migrated.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModePerLanguage, migrated.AudioKeepMode);
        Assert.Equal(2, migrated.SubtitleMaxPerLanguage);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyImageFirst, migrated.SubtitleQualityStrategy);
        Assert.True(migrated.StandardizeTrackNames);
        Assert.Equal("{language} {codec}", migrated.TrackNameTemplate);
        Assert.Equal("F", migrated.TrackNameOverrides.Forced);
        Assert.Equal("HI", migrated.TrackNameOverrides.HearingImpaired);
        Assert.Equal("C", migrated.TrackNameOverrides.Commentary);
        Assert.Equal("AD", migrated.TrackNameOverrides.AudioDescription);
        Assert.True(migrated.ClearVideoTrackNames);
        Assert.True(migrated.RemoveChapters);

        var legacy = await LibraryStore.GetRuleSetByNameAsync(uow, "Legacy");
        Assert.Equal("""[{"field":"forced","value":null,"reversed":false}]""", legacy!.SubtitleSortersJson);
        Assert.False(legacy.RemoveHearingImpairedSubs);
        Assert.Equal(RemuxRuleValues.AudioKeepModeSingle, legacy.AudioKeepMode);
        Assert.Equal(0, legacy.SubtitleMaxPerLanguage);
        Assert.Equal(RemuxRuleValues.SubtitleStrategyTextFirst, legacy.SubtitleQualityStrategy);
        Assert.Equal(TrackNaming.DefaultTemplate, legacy.TrackNameTemplate);
        Assert.Equal(new TrackNameOverrides(), legacy.TrackNameOverrides);

        var blank = await LibraryStore.GetRuleSetByNameAsync(uow, "Blank");
        Assert.Equal(string.Empty, blank!.SubtitleSortersJson);
        Assert.False(blank.RemoveHearingImpairedSubs);
    }

    [Fact]
    public async Task Library_mode_settings_job_row_migrates_into_columns_and_library_folders_and_the_row_is_retired()
    {
        Execute("INSERT INTO refiner_libraries (id, name) VALUES (1, 'Movies')");
        Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES (@key, 'refiner.library.settings.v1', @payload, 'completed')",
            ("@key", "refiner.library.settings.v1:1"),
            ("@payload",
                """{"library_id":1,"library_folders":["/lib/a","/lib/b"],"library_schedule_enabled":true,"clean_hardlinked_files":true,"skip_if_manager_would_redownload":false}"""));

        Upgrade();

        await using var uow = await UnitOfWork.OpenAsync(_database);
        var settings = await LibrarySettingsStore.GetAsync(uow, 1);
        Assert.Equal(["/lib/a", "/lib/b"], settings.Folders);
        Assert.True(settings.ScheduleEnabled);
        Assert.True(settings.CleanHardlinkedFiles);
        Assert.False(settings.SkipIfManagerWouldRedownload);

        Assert.Equal(0L, Convert.ToInt64(Scalar("SELECT COUNT(*) FROM jobs WHERE job_kind = 'processing.library.settings.v1'"), System.Globalization.CultureInfo.InvariantCulture));
    }

    [Fact]
    public async Task A_library_with_no_settings_row_keeps_the_documented_defaults()
    {
        Execute("INSERT INTO refiner_libraries (id, name) VALUES (1, 'Movies')");

        Upgrade();

        await using var uow = await UnitOfWork.OpenAsync(_database);
        var settings = await LibrarySettingsStore.GetAsync(uow, 1);
        Assert.Empty(settings.Folders);
        Assert.False(settings.ScheduleEnabled);
        Assert.False(settings.CleanHardlinkedFiles);
        Assert.True(settings.SkipIfManagerWouldRedownload);
    }

    [Fact]
    public async Task Library_scan_files_and_551_manager_matches_migrate_into_library_files()
    {
        Execute("INSERT INTO refiner_libraries (id, name) VALUES (1, 'Movies')");
        Execute("INSERT INTO media_manager_connections (id, kind, name) VALUES (5, 'radarr', 'Radarr')");
        Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES (@key, 'refiner.library.scan.v1', @payload, 'completed')",
            ("@key", "refiner.library.scan.v1:1:abc"),
            ("@payload",
                """
                {"library_id":1,"trigger":"manual","ok":true,"scan_result":{"generated_at":1700000000,"files":[
                {"path":"Movie/film.mkv","size_bytes":123,"mtime":456,"classification":"would_change",
                "summary":"Removes 1 track","reason":null,"removed_audio_tracks":1,"removed_subtitle_tracks":0,
                "manager_kind":"radarr","manager_title":"Movie","probe_json":"{\"streams\":[]}",
                "estimated_bytes_saved":789,"manager_connection_id":5,"manager_title_id":"42","manager_file_id":7,
                "manager_quality_profile_id":3}],"errors":["Weir could not ask Sonarr which titles it manages: timed out"]}}
                """));

        Upgrade();

        await using var uow = await UnitOfWork.OpenAsync(_database);
        var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, 1);
        Assert.NotNull(snapshot);
        Assert.Equal(DateTimeOffset.FromUnixTimeSeconds(1700000000), snapshot!.GeneratedAt);
        Assert.Equal(["Weir could not ask Sonarr which titles it manages: timed out"], snapshot.Errors);
        var file = Assert.Single(snapshot.Files);
        Assert.Equal("Movie/film.mkv", file.Path);
        Assert.Equal(123, file.SizeBytes);
        Assert.Equal(456, file.ModifiedTimeUnixSeconds);
        Assert.Equal(LibraryFileClassification.WouldChange, file.Classification);
        Assert.Equal("Removes 1 track", file.Summary);
        Assert.Equal(1, file.RemovedAudioCount);
        Assert.Equal(0, file.RemovedSubtitleCount);
        Assert.Equal("radarr", file.ManagerKind);
        Assert.Equal("Movie", file.ManagerTitle);
        Assert.Equal(5, file.ManagerConnectionId);
        Assert.Equal("42", file.ManagerTitleId);
        Assert.Equal(7, file.ManagerFileId);
        Assert.Equal(3, file.ManagerQualityProfileId);
        Assert.Equal(789, file.EstimatedBytesSaved);

        // The bulky array is stripped from the job row; the small ok/generated_at/errors outcome stays.
        var remainingPayload = (string)Scalar("SELECT payload_json FROM jobs WHERE dedupe_key = 'processing.library.scan.v1:1:abc'")!;
        Assert.DoesNotContain("\"files\"", remainingPayload, StringComparison.Ordinal);
        Assert.Contains("\"generated_at\":1700000000", remainingPayload, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Swap_journal_keys_migrate_into_library_swaps_and_are_stripped_from_the_payload()
    {
        Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES ('clean:1', 'refiner.library.clean.v1', @payload, 'leased')",
            ("@payload",
                """
                {"library_id":1,"path":"Movie/film.mkv","library_swap":{"state":"committed",
                "original_path":"/lib/film.mkv","temp_path":"/lib/film.weir-tmp.mkv","backup_path":"/lib/film.weir-bak.mkv"},
                "swap_committed":true}
                """));
        var jobId = (long)Scalar("SELECT id FROM refiner_jobs WHERE dedupe_key = 'clean:1'")!;

        Upgrade();

        var journal = new ProcessingJobSwapJournal(_database);
        var unfinished = await journal.ListUnfinishedAsync();
        var entry = Assert.Single(unfinished);
        Assert.Equal(jobId, entry.JobId);
        Assert.Equal("/lib/film.mkv", entry.OriginalPath);
        Assert.Equal(SwapJournalState.Committed, entry.State);

        var remainingPayload = (string)Scalar("SELECT payload_json FROM jobs WHERE id = @id", ("@id", jobId))!;
        Assert.DoesNotContain("library_swap", remainingPayload, StringComparison.Ordinal);
        Assert.DoesNotContain("swap_committed", remainingPayload, StringComparison.Ordinal);
        Assert.Contains("\"path\":\"Movie/film.mkv\"", remainingPayload, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Removed_track_records_migrate_from_both_the_structured_shape_and_the_legacy_free_text_lists()
    {
        Execute("INSERT INTO refiner_libraries (id, name) VALUES (1, 'Movies')");
        Execute(
            "INSERT INTO refiner_file_logs (library_id, relative_path, outcome, detail_json) VALUES (1, 'A.mkv', 'library.removed_tracks', @detail)",
            ("@detail",
                """
                {"removed_track_records":[
                {"language":"jpn","type":"audio","codec":"aac","variant":"kansai","reason":"not selected"},
                {"language":"spa","type":"subtitle","codec":"srt","reason":"language not wanted"}]}
                """));
        Execute(
            "INSERT INTO refiner_file_logs (library_id, relative_path, outcome, detail_json) VALUES (NULL, 'B.mkv', 'refiner.file.remux_pass.v1', @detail)",
            ("@detail", """{"removed_audio":["jpn: removed (not selected — eng dts kept)"],"removed_subtitles":["spa"]}"""));

        Upgrade();

        var store = new FileLogRemovedTrackStore(_database);
        var structured = await store.GetAsync(new RemovedTrackFileKey(1, "A.mkv"));
        Assert.Equal(2, structured.Count);
        Assert.Equal("jpn", structured[0].Language);
        Assert.Equal(RemovedTrackType.Audio, structured[0].Type);
        Assert.Equal("aac", structured[0].Codec);
        Assert.Equal("kansai", structured[0].Variant);
        Assert.Equal("spa", structured[1].Language);
        Assert.Equal(RemovedTrackType.Subtitle, structured[1].Type);

        var legacy = await store.GetAsync(new RemovedTrackFileKey(null, "B.mkv"));
        Assert.Equal(2, legacy.Count);
        Assert.Equal("jpn", legacy[0].Language);
        Assert.Equal(RemovedTrackType.Audio, legacy[0].Type);
        Assert.Equal("unknown", legacy[0].Codec);
        Assert.Equal("spa", legacy[1].Language);
        Assert.Equal(RemovedTrackType.Subtitle, legacy[1].Type);
    }

    [Fact]
    public async Task Job_row_and_file_log_retention_can_no_longer_delete_migrated_settings_scan_index_or_removed_track_data()
    {
        const string ancient = "2000-01-01 00:00:00";
        Execute("INSERT INTO refiner_libraries (id, name) VALUES (1, 'Movies')");
        Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, updated_at) VALUES (@key, 'refiner.library.settings.v1', @payload, 'completed', @updated)",
            ("@key", "refiner.library.settings.v1:1"),
            ("@payload", """{"library_id":1,"library_folders":["/lib/a"],"library_schedule_enabled":true}"""),
            ("@updated", ancient));
        Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, updated_at) VALUES (@key, 'refiner.library.scan.v1', @payload, 'completed', @updated)",
            ("@key", "refiner.library.scan.v1:1:abc"),
            ("@payload",
                """{"library_id":1,"ok":true,"scan_result":{"generated_at":946684800,"files":[{"path":"A.mkv","size_bytes":1,"mtime":1,"classification":"matches"}],"errors":[]}}"""),
            ("@updated", ancient));
        Execute(
            "INSERT INTO refiner_file_logs (library_id, relative_path, outcome, detail_json, recorded_at) VALUES (1, 'A.mkv', 'library.removed_tracks', @detail, @recorded)",
            ("@detail", """{"removed_track_records":[{"language":"jpn","type":"audio","codec":"aac","reason":"not selected"}]}"""),
            ("@recorded", ancient));

        Upgrade();

        // An aggressive retention window: everything terminal in refiner_jobs, and every refiner_file_logs
        // row, is due for pruning.
        var jobStore = new ProcessingJobStore(_database, TimeProvider.System);
        await JobRowsRetention.RunTickAsync(jobStore, jobRowsRetentionDays: 0, DateTimeOffset.UtcNow);
        await using (var pruneUow = await UnitOfWork.OpenAsync(_database))
        {
            await FileLogStore.PruneAsync(pruneUow, retentionDays: 0, DateTimeOffset.UtcNow);
            await pruneUow.CommitAsync();
        }

        // The scan job row (a job's own bookkeeping) may now be gone, but the file index it produced is not.
        await using var uow = await UnitOfWork.OpenAsync(_database);
        var settings = await LibrarySettingsStore.GetAsync(uow, 1);
        Assert.Equal(["/lib/a"], settings.Folders);
        Assert.True(settings.ScheduleEnabled);

        var snapshot = await LibraryScanStore.LatestSnapshotAsync(uow, 1);
        Assert.NotNull(snapshot);
        Assert.Equal("A.mkv", Assert.Single(snapshot!.Files).Path);

        var removedTrackStore = new FileLogRemovedTrackStore(_database);
        var tracks = await removedTrackStore.GetAsync(new RemovedTrackFileKey(1, "A.mkv"));
        Assert.Equal("jpn", Assert.Single(tracks).Language);
    }
}
