using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Sqlite.Migrations;

/// <summary>
/// Issue #568's migration (<c>0007_library_file_facets.sql</c>) back-fills the Library view's codec, resolution
/// and language facts from the ffprobe JSON already on each <c>library_files</c> row, so an existing install does
/// not have to rescan before the view has anything to show.
///
/// <para>The back-fill is SQL, and the live path is
/// <see cref="LibraryFileFactsReader"/>; the two would drift silently, so every test here compares the migrated
/// rows against what the C# reader produces for the same probe JSON rather than against hand-written expectations.
/// A change to either needs the same change to the other.</para>
///
/// <para>Each test starts at the frozen baseline (the pre-#557 head, which has no <c>library_files</c> table at
/// all), seeds a completed scan job in the shape #557's own migration reads, and upgrades to head — so the row
/// under test arrives the way a real upgrade would deliver it, through <c>0004</c> and then <c>0007</c>.</para>
/// </summary>
public sealed class Issue568MigrationTests : IDisposable
{
    private const string FilmProbe = """
    {"streams": [
      {"index": 0, "codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160},
      {"index": 1, "codec_type": "audio", "codec_name": "eac3", "channels": 6, "channel_layout": "5.1(side)", "tags": {"language": "eng"}},
      {"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "channel_layout": "stereo", "tags": {"language": "ja"}},
      {"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "pt-BR"}},
      {"index": 4, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle", "tags": {"language": "und"}}
    ]}
    """;

    private const string PosterFirstProbe = """
    {"streams": [
      {"index": 0, "codec_type": "video", "codec_name": "mjpeg", "width": 600, "height": 900, "disposition": {"attached_pic": 1}},
      {"index": 1, "codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
      {"index": 2, "codec_type": "audio", "codec_name": "dts", "channels": 8, "tags": {"language": "fre"}},
      {"index": 3, "codec_type": "audio", "codec_name": "aac", "channels": 3},
      {"index": 4, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "spa"}},
      {"index": 5, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "ita"}}
    ]}
    """;

    private readonly TempDirectory _temp = new();
    private readonly SqliteDatabase _database;

    public Issue568MigrationTests()
    {
        _database = new SqliteDatabase(_temp.Join("weir.sqlite3"));
        Assert.Equal(SchemaStartupOutcome.Created, new SchemaMigrator(_database).EnsureAtBaseline());
        Execute("DELETE FROM refiner_libraries;");
        Execute(
            "INSERT INTO refiner_libraries (id, name, media_type, watched_folder, output_folder, work_folder, display_order) " +
            "VALUES (1, 'Movies library', 'movie', '/in', '/out', '/work', 1)");
    }

    public void Dispose()
    {
        _database.ClearPool();
        _temp.Dispose();
    }

    /// <summary>Seeds the completed scan job #557's <c>0004</c> migration copies into <c>library_files</c>.</summary>
    private void SeedScan(params (string Path, string ProbeJson, string Classification, string? Reason)[] files)
    {
        var entries = files.Select(file => new PyDictLike(file.Path, file.ProbeJson, file.Classification, file.Reason).ToJson());
        Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, created_at, updated_at) " +
            "VALUES ('refiner.library.scan.v1:1:seed', 'refiner.library.scan.v1', @payload, 'completed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            ("@payload",
                "{\"library_id\": 1, \"trigger\": \"manual\", \"ok\": true, \"scan_result\": {\"generated_at\": 1700000000, \"errors\": [], " +
                "\"files\": [" + string.Join(", ", entries) + "]}}"));
    }

    private sealed record PyDictLike(string Path, string ProbeJson, string Classification, string? Reason)
    {
        public string ToJson() =>
            "{\"path\": " + Quote(Path) + ", \"size_bytes\": 1000, \"mtime\": 1700000000, \"classification\": " +
            Quote(Classification) + ", \"reason\": " + (Reason is null ? "null" : Quote(Reason)) +
            ", \"removed_audio_tracks\": 0, \"removed_subtitle_tracks\": 0, \"estimated_bytes_saved\": 0, " +
            "\"probe_json\": " + Quote(ProbeJson) + "}";

        private static string Quote(string value) => System.Text.Json.JsonSerializer.Serialize(value);
    }

    private void Upgrade() => Assert.Equal(SchemaStartupOutcome.Upgraded, new SchemaMigrator(_database).EnsureAtHead());

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

    private List<T> Query<T>(string sql, Func<SqliteDataReader, T> map)
    {
        using var connection = _database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        using var reader = command.ExecuteReader();
        var rows = new List<T>();
        while (reader.Read())
        {
            rows.Add(map((SqliteDataReader)reader));
        }

        return rows;
    }

    private List<(string Facet, string Value)> FacetsOf(string path) => Query(
        "SELECT x.facet, x.value FROM library_file_facets AS x JOIN library_files AS f ON f.id = x.library_file_id " +
        "WHERE f.path = " + System.Text.Json.JsonSerializer.Serialize(path).Replace('"', '\'') + " ORDER BY x.facet, x.value",
        reader => (reader.GetString(0), reader.GetString(1)));

    private static List<(string Facet, string Value)> ExpectedFacets(string probeJson) =>
        LibraryFileFactsReader.Derive(probeJson).Facets
            .Select(facet => (facet.Facet, facet.Value))
            .OrderBy(pair => pair.Facet, StringComparer.Ordinal)
            .ThenBy(pair => pair.Value, StringComparer.Ordinal)
            .ToList();

    [Fact]
    public void The_back_fill_derives_exactly_what_a_scan_would_have_recorded()
    {
        SeedScan(("/lib/film.mkv", FilmProbe, "would_change", null), ("/lib/show.mkv", PosterFirstProbe, "matches", null));

        Upgrade();

        foreach (var (path, probe) in new[] { ("/lib/film.mkv", FilmProbe), ("/lib/show.mkv", PosterFirstProbe) })
        {
            var expected = LibraryFileFactsReader.Derive(probe);
            var actual = Query(
                "SELECT video_codec, video_height, resolution_class, audio_track_count, subtitle_track_count, audio_summary, " +
                "subtitle_summary FROM library_files WHERE path = '" + path + "'",
                reader => (
                    Codec: reader.GetString(0),
                    Height: reader.IsDBNull(1) ? (int?)null : (int)reader.GetInt64(1),
                    Resolution: reader.GetString(2),
                    AudioTracks: (int)reader.GetInt64(3),
                    SubtitleTracks: (int)reader.GetInt64(4),
                    AudioSummary: reader.IsDBNull(5) ? null : reader.GetString(5),
                    SubtitleSummary: reader.IsDBNull(6) ? null : reader.GetString(6))).Single();

            Assert.Equal(expected.VideoCodec, actual.Codec);
            Assert.Equal(expected.VideoHeight, actual.Height);
            Assert.Equal(expected.ResolutionClass, actual.Resolution);
            Assert.Equal(expected.AudioTrackCount, actual.AudioTracks);
            Assert.Equal(expected.SubtitleTrackCount, actual.SubtitleTracks);
            Assert.Equal(expected.AudioSummary, actual.AudioSummary);
            Assert.Equal(expected.SubtitleSummary, actual.SubtitleSummary);
            Assert.Equal(ExpectedFacets(probe), FacetsOf(path));
        }
    }

    [Fact]
    public void A_two_letter_language_tag_lands_on_the_same_breakdown_row_as_its_three_letter_spelling()
    {
        SeedScan(("/lib/film.mkv", FilmProbe, "matches", null));

        Upgrade();

        var facets = FacetsOf("/lib/film.mkv");
        // "ja" (audio) and "pt-BR" (subtitle) are the input spellings; the breakdown must show jpn and por.
        Assert.Contains((LibraryFacets.AudioLanguage, "jpn"), facets);
        Assert.Contains((LibraryFacets.SubtitleLanguage, "por"), facets);
        Assert.DoesNotContain((LibraryFacets.AudioLanguage, "ja"), facets);
        Assert.Contains((LibraryFacets.SubtitleLanguage, "unknown"), facets);
    }

    [Fact]
    public void A_row_with_no_usable_probe_reads_unknown_instead_of_an_empty_cell()
    {
        SeedScan(("/lib/broken.mkv", "", "cannot_process", "Weir could not read this file: ffprobe exited 1"));

        Upgrade();

        var row = Query(
            "SELECT video_codec, resolution_class, video_height, audio_track_count, problem_kind FROM library_files WHERE path = '/lib/broken.mkv'",
            reader => (reader.GetString(0), reader.GetString(1), reader.IsDBNull(2), (int)reader.GetInt64(3), reader.GetString(4))).Single();

        Assert.Equal((LibraryFileFacts.Unknown, LibraryFileFacts.Unknown, true, 0, "unreadable"), row);
        Assert.Equal(
            [(LibraryFacets.Resolution, LibraryFileFacts.Unknown), (LibraryFacets.VideoCodec, LibraryFileFacts.Unknown)],
            FacetsOf("/lib/broken.mkv"));
    }

    [Fact]
    public void An_already_recorded_reason_is_grouped_under_the_problem_it_names()
    {
        SeedScan(
            ("/lib/novideo.mkv", "{\"streams\": []}", "cannot_process", "This file has no video track that Weir could find."),
            ("/lib/noaudio.mkv", FilmProbe, "cannot_process", "No audio track would remain after applying this library's rules, so Weir will not touch this file."),
            ("/lib/fine.mkv", FilmProbe, "matches", null));

        Upgrade();

        var kinds = Query(
            "SELECT path, COALESCE(problem_kind, '') FROM library_files ORDER BY path",
            reader => (reader.GetString(0), reader.GetString(1)));

        Assert.Equal(
            [("/lib/fine.mkv", ""), ("/lib/noaudio.mkv", "no_audio_left"), ("/lib/novideo.mkv", "no_video")],
            kinds);
    }

    [Fact]
    public void The_head_revision_is_recorded_and_the_indexes_the_view_reads_through_exist()
    {
        SeedScan(("/lib/film.mkv", FilmProbe, "matches", null));

        Upgrade();

        Assert.Equal(
            SchemaMigrator.HeadRevision,
            Query("SELECT version_num FROM alembic_version", reader => reader.GetString(0)).Single());
        var indexes = Query("SELECT name FROM sqlite_master WHERE type = 'index' ORDER BY name", reader => reader.GetString(0));
        Assert.Contains("ix_library_file_facets_library_id_facet_value", indexes);
        Assert.Contains("ix_library_file_facets_library_file_id", indexes);
        Assert.Contains("ix_library_files_library_id_size_bytes", indexes);
    }

    [Fact]
    public void A_database_with_no_scan_history_upgrades_without_a_row_to_back_fill()
    {
        Upgrade();

        Assert.Equal(0L, Convert.ToInt64(ScalarOf("SELECT COUNT(*) FROM library_files"), CultureInfo.InvariantCulture));
        Assert.Equal(0L, Convert.ToInt64(ScalarOf("SELECT COUNT(*) FROM library_file_facets"), CultureInfo.InvariantCulture));
    }

    private object? ScalarOf(string sql)
    {
        using var connection = _database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return command.ExecuteScalar();
    }
}
