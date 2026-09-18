using System.Globalization;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.Platform;

namespace Weir.Infrastructure.Tests.LibraryMode;

/// <summary>
/// Issue #568: the Library view's totals, breakdowns, paged/sorted/filtered Files listing and Problems grouping,
/// against a real database. Every scan row is written through the real store, so the facts and facet rows under
/// test are the ones a scan actually produces from its cached ffprobe JSON.
/// </summary>
public sealed class LibraryViewStoreTests : IDisposable
{
    private readonly StoreFixture _store = new();
    private long _libraryId;

    public void Dispose() => _store.Dispose();

    private static string Probe(string videoCodec, int height, params (string Kind, string Codec, int Channels, string Language)[] tracks)
    {
        var width = height * 16 / 9;
        var streams = new List<string>
        {
            "{\"codec_type\": \"video\", \"codec_name\": \"" + videoCodec + "\", \"width\": " +
            width.ToString(CultureInfo.InvariantCulture) + ", \"height\": " + height.ToString(CultureInfo.InvariantCulture) + "}",
        };
        streams.AddRange(tracks.Select(track => track.Kind == "audio"
            ? "{\"codec_type\": \"audio\", \"codec_name\": \"" + track.Codec + "\", \"channels\": " +
                track.Channels.ToString(CultureInfo.InvariantCulture) + ", \"tags\": {\"language\": \"" + track.Language + "\"}}"
            : "{\"codec_type\": \"subtitle\", \"codec_name\": \"" + track.Codec + "\", \"tags\": {\"language\": \"" + track.Language + "\"}}"));
        return "{\"streams\": [" + string.Join(", ", streams) + "], \"format\": {\"duration\": \"5400.0\"}}";
    }

    private async Task<long> LibraryAsync()
    {
        _libraryId = Convert.ToInt64(
            await _store.WithUnitOfWork(uow => uow.ExecuteScalarWriteAsync(
                "INSERT INTO libraries (name, media_type, watched_folder, output_folder, work_folder, display_order) " +
                // The schema seeds default libraries; this one needs a name of its own (the column is unique).
                "VALUES ('Library view tests', 'movie', '/in', '/out', '/work', 1) RETURNING id")),
            CultureInfo.InvariantCulture);
        return _libraryId;
    }

    /// <summary>Writes a scan snapshot through the real store, which is what derives the facts and facet rows.</summary>
    private async Task RecordAsync(params LibraryScanFileEntry[] files) =>
        await _store.WithUnitOfWork(async uow =>
        {
            var jobId = Convert.ToInt64(
                await uow.ExecuteScalarWriteAsync(
                    "INSERT INTO jobs (dedupe_key, job_kind, payload_json, status, created_at, updated_at) " +
                    "VALUES (@key, 'processing.library.scan.v1', '{}', 'completed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id",
                    ("@key", LibraryModeJobKinds.ScanDedupeKey(_libraryId))),
                CultureInfo.InvariantCulture);
            await LibraryScanStore.RecordResultAsync(
                uow, jobId, new LibraryScanSnapshot(_libraryId, DateTimeOffset.UnixEpoch.AddSeconds(1_700_000_000), files, []), true, null);
            return 0;
        });

    private static LibraryScanFileEntry File(
        string path,
        LibraryFileClassification classification,
        string probeJson,
        long sizeBytes = 1_000_000,
        long savedBytes = 0,
        int removedAudio = 0,
        LibraryProblemKind? problem = null,
        int? linkCount = null,
        string? managerKind = null,
        string? managerTitle = null) =>
        new(path, sizeBytes, 1_700_000_000, classification, null, null, removedAudio, 0, managerKind, managerTitle,
            probeJson, savedBytes, null, null, null, null, problem, linkCount);

    private Task<T> Read<T>(Func<UnitOfWork, Task<T>> work) => _store.WithUnitOfWork(work, commit: false);

    [Fact]
    public async Task Totals_count_every_file_its_size_and_what_the_rules_would_do()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080, ("audio", "aac", 2, "eng")), sizeBytes: 100),
            File("/lib/b.mkv", LibraryFileClassification.WouldChange, Probe("hevc", 2160, ("audio", "eac3", 6, "eng")), sizeBytes: 200, savedBytes: 50, removedAudio: 2),
            File("/lib/c.mkv", LibraryFileClassification.CannotProcess, "", sizeBytes: 300, problem: LibraryProblemKind.Unreadable));

        var totals = await Read(uow => LibraryViewStore.TotalsAsync(uow, _libraryId));

        Assert.Equal(3, totals.Files);
        Assert.Equal(600, totals.SizeBytes);
        Assert.Equal(1, totals.Matches);
        Assert.Equal(1, totals.WouldChange);
        Assert.Equal(1, totals.CannotProcess);
        Assert.Equal(50, totals.EstimatedBytesSaved);
        Assert.Equal(2, totals.RemovedAudioTracks);
    }

    [Fact]
    public async Task A_breakdown_counts_files_not_tracks_and_orders_the_biggest_group_first()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080, ("audio", "aac", 2, "eng"), ("audio", "ac3", 6, "eng")), sizeBytes: 10),
            File("/lib/b.mkv", LibraryFileClassification.Matches, Probe("h264", 1080, ("audio", "aac", 2, "eng")), sizeBytes: 20),
            File("/lib/c.mkv", LibraryFileClassification.Matches, Probe("hevc", 2160, ("audio", "eac3", 6, "jpn")), sizeBytes: 30));

        var codecs = await Read(uow => LibraryViewStore.BreakdownAsync(uow, _libraryId, LibraryFacets.VideoCodec));
        var languages = await Read(uow => LibraryViewStore.BreakdownAsync(uow, _libraryId, LibraryFacets.AudioLanguage));
        var resolutions = await Read(uow => LibraryViewStore.BreakdownAsync(uow, _libraryId, LibraryFacets.Resolution));

        Assert.Equal([new LibraryBreakdownRow("h264", 2, 30), new LibraryBreakdownRow("hevc", 1, 30)], codecs);
        // "a.mkv" has two English audio tracks and still counts once.
        Assert.Equal([new LibraryBreakdownRow("eng", 2, 30), new LibraryBreakdownRow("jpn", 1, 30)], languages);
        Assert.Equal([new LibraryBreakdownRow("1080p", 2, 30), new LibraryBreakdownRow("4k", 1, 30)], resolutions);
    }

    [Fact]
    public async Task An_unknown_facet_name_never_reaches_the_sql()
    {
        await LibraryAsync();
        await RecordAsync(File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080, ("audio", "aac", 2, "eng"))));

        Assert.Empty(await Read(uow => LibraryViewStore.BreakdownAsync(uow, _libraryId, "path'; DROP TABLE library_files; --")));
    }

    [Fact]
    public async Task A_facet_filter_narrows_the_files_listing_and_its_totals()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080, ("audio", "aac", 2, "eng")), sizeBytes: 10),
            File("/lib/b.mkv", LibraryFileClassification.WouldChange, Probe("hevc", 2160, ("audio", "eac3", 6, "eng"), ("audio", "aac", 2, "jpn")), sizeBytes: 20),
            File("/lib/c.mkv", LibraryFileClassification.Matches, Probe("hevc", 2160, ("audio", "eac3", 6, "fre")), sizeBytes: 40));

        var japanese = new LibraryFileQuery { Facets = [new LibraryFileFacet(LibraryFacets.AudioLanguage, "jpn")] };
        var files = await Read(uow => LibraryViewStore.ListFilesAsync(uow, _libraryId, japanese));
        var totals = await Read(uow => LibraryViewStore.TotalsAsync(uow, _libraryId, japanese));

        Assert.Equal(["/lib/b.mkv"], files.Select(f => f.Path));
        Assert.Equal(1, totals.Files);
        Assert.Equal(20, totals.SizeBytes);
    }

    [Fact]
    public async Task Two_facet_filters_are_both_required_of_a_file()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("hevc", 2160, ("audio", "eac3", 6, "eng"))),
            File("/lib/b.mkv", LibraryFileClassification.Matches, Probe("h264", 2160, ("audio", "eac3", 6, "eng"))),
            File("/lib/c.mkv", LibraryFileClassification.Matches, Probe("hevc", 1080, ("audio", "eac3", 6, "eng"))));

        var files = await Read(uow => LibraryViewStore.ListFilesAsync(uow, _libraryId, new LibraryFileQuery
        {
            Facets = [new LibraryFileFacet(LibraryFacets.VideoCodec, "hevc"), new LibraryFileFacet(LibraryFacets.Resolution, "4k")],
        }));

        Assert.Equal(["/lib/a.mkv"], files.Select(f => f.Path));
    }

    [Fact]
    public async Task The_search_matches_a_path_or_a_managers_own_title()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/blade.mkv", LibraryFileClassification.Matches, Probe("h264", 1080), managerKind: "radarr", managerTitle: "Blade Runner 2049"),
            File("/lib/arrival.mkv", LibraryFileClassification.Matches, Probe("h264", 1080)));

        var byTitle = await Read(uow => LibraryViewStore.ListFilesAsync(uow, _libraryId, new LibraryFileQuery { Search = "runner" }));
        var byPath = await Read(uow => LibraryViewStore.ListFilesAsync(uow, _libraryId, new LibraryFileQuery { Search = "arriv" }));

        Assert.Equal(["/lib/blade.mkv"], byTitle.Select(f => f.Path));
        Assert.Equal(["/lib/arrival.mkv"], byPath.Select(f => f.Path));
    }

    [Fact]
    public async Task Sorting_and_paging_return_each_row_exactly_once_in_the_asked_for_order()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080), sizeBytes: 300),
            File("/lib/b.mkv", LibraryFileClassification.Matches, Probe("h264", 1080), sizeBytes: 100),
            File("/lib/c.mkv", LibraryFileClassification.Matches, Probe("h264", 1080), sizeBytes: 200),
            File("/lib/d.mkv", LibraryFileClassification.Matches, Probe("h264", 1080), sizeBytes: 200));

        var bySize = new LibraryFileQuery { Sort = "size", Descending = true, PageSize = 2 };
        var page1 = await Read(uow => LibraryViewStore.ListFilesAsync(uow, _libraryId, bySize));
        var page2 = await Read(uow => LibraryViewStore.ListFilesAsync(uow, _libraryId, bySize with { Page = 2 }));
        var count = await Read(uow => LibraryViewStore.CountFilesAsync(uow, _libraryId, bySize));

        Assert.Equal(4, count);
        // 200 is a tie between c and d; the path tie-break keeps the two pages from overlapping.
        Assert.Equal(["/lib/a.mkv", "/lib/c.mkv"], page1.Select(f => f.Path));
        Assert.Equal(["/lib/d.mkv", "/lib/b.mkv"], page2.Select(f => f.Path));
    }

    [Fact]
    public async Task An_unknown_sort_key_falls_back_to_the_path_rather_than_reaching_the_sql()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/b.mkv", LibraryFileClassification.Matches, Probe("h264", 1080)),
            File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080)));

        var files = await Read(uow => LibraryViewStore.ListFilesAsync(
            uow, _libraryId, new LibraryFileQuery { Sort = "size_bytes; DROP TABLE library_files" }));

        Assert.Equal(["/lib/a.mkv", "/lib/b.mkv"], files.Select(f => f.Path));
    }

    [Fact]
    public async Task A_files_row_carries_the_media_facts_the_table_shows()
    {
        await LibraryAsync();
        await RecordAsync(File(
            "/lib/a.mkv",
            LibraryFileClassification.WouldChange,
            Probe("hevc", 2160, ("audio", "eac3", 6, "eng"), ("audio", "aac", 2, "jpn"), ("subtitle", "subrip", 0, "eng")),
            managerKind: "radarr",
            managerTitle: "Blade Runner 2049"));

        var row = Assert.Single(await Read(uow => LibraryViewStore.ListFilesAsync(uow, _libraryId, new LibraryFileQuery())));

        Assert.Equal("hevc", row.VideoCodec);
        Assert.Equal("4k", row.ResolutionClass);
        Assert.Equal(2160, row.VideoHeight);
        Assert.Equal(2, row.AudioTrackCount);
        Assert.Equal(1, row.SubtitleTrackCount);
        Assert.Equal("eng eac3 5.1, jpn aac stereo", row.AudioSummary);
        Assert.Equal("eng", row.SubtitleSummary);
        Assert.Equal("Blade Runner 2049", row.ManagerTitle);
    }

    [Fact]
    public async Task Problems_group_by_reason_and_leave_out_a_kind_with_no_files()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/ok.mkv", LibraryFileClassification.WouldChange, Probe("h264", 1080, ("audio", "aac", 2, "eng"))),
            File("/lib/broken.mkv", LibraryFileClassification.CannotProcess, "", problem: LibraryProblemKind.Unreadable, sizeBytes: 7),
            File("/lib/locked.mkv", LibraryFileClassification.CannotProcess, "", problem: LibraryProblemKind.NoPermission),
            File("/lib/seeding.mkv", LibraryFileClassification.WouldChange, Probe("h264", 1080, ("audio", "aac", 2, "eng")), linkCount: 2));

        var groups = await Read(uow => LibraryViewStore.ProblemsAsync(uow, _libraryId, cleanHardlinkedFiles: false));

        Assert.Equal(
            [LibraryProblemKind.Seeding, LibraryProblemKind.NoPermission, LibraryProblemKind.Unreadable],
            groups.Select(g => g.Kind));
        Assert.Equal(["/lib/seeding.mkv"], groups[0].SampleFiles);
        Assert.Equal(7, groups[2].SizeBytes);
        Assert.DoesNotContain(groups, g => g.Kind == LibraryProblemKind.NoVideo);
    }

    [Fact]
    public async Task A_library_that_allows_hardlinked_files_never_reports_seeding_as_a_problem()
    {
        await LibraryAsync();
        await RecordAsync(File("/lib/seeding.mkv", LibraryFileClassification.WouldChange, Probe("h264", 1080), linkCount: 3));

        Assert.Empty(await Read(uow => LibraryViewStore.ProblemsAsync(uow, _libraryId, cleanHardlinkedFiles: true)));
        Assert.Single(await Read(uow => LibraryViewStore.ProblemsAsync(uow, _libraryId, cleanHardlinkedFiles: false)));
    }

    [Fact]
    public async Task A_cleans_preflight_note_is_recorded_on_the_file_and_never_overwrites_a_scans_own_verdict()
    {
        await LibraryAsync();
        await RecordAsync(
            File("/lib/risky.mkv", LibraryFileClassification.WouldChange, Probe("h264", 1080, ("audio", "aac", 2, "eng"))),
            File("/lib/broken.mkv", LibraryFileClassification.CannotProcess, "", problem: LibraryProblemKind.Unreadable));

        await _store.WithUnitOfWork(async uow =>
        {
            await LibraryViewStore.RecordPreflightProblemAsync(uow, _libraryId, "/lib/risky.mkv", LibraryProblemKind.ManagerRedownload);
            await LibraryViewStore.RecordPreflightProblemAsync(uow, _libraryId, "/lib/broken.mkv", null);
            return 0;
        });

        var groups = await Read(uow => LibraryViewStore.ProblemsAsync(uow, _libraryId, cleanHardlinkedFiles: false));

        Assert.Equal(["/lib/risky.mkv"], Assert.Single(groups, g => g.Kind == LibraryProblemKind.ManagerRedownload).SampleFiles);
        Assert.Equal(["/lib/broken.mkv"], Assert.Single(groups, g => g.Kind == LibraryProblemKind.Unreadable).SampleFiles);
    }

    [Fact]
    public async Task A_rescan_replaces_a_librarys_facet_rows_rather_than_adding_to_them()
    {
        await LibraryAsync();
        await RecordAsync(File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080, ("audio", "aac", 2, "eng"))));
        await RecordAsync(File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("hevc", 2160, ("audio", "eac3", 6, "jpn"))));

        var codecs = await Read(uow => LibraryViewStore.BreakdownAsync(uow, _libraryId, LibraryFacets.VideoCodec));
        var orphans = await Read(uow => uow.CountAsync(
            "SELECT COUNT(*) FROM library_file_facets WHERE library_file_id NOT IN (SELECT id FROM library_files)"));

        Assert.Equal([new LibraryBreakdownRow("hevc", 1, 1_000_000)], codecs);
        Assert.Equal(0, orphans);
    }

    [Fact]
    public async Task Deleting_a_library_takes_its_facet_rows_with_it()
    {
        await LibraryAsync();
        await RecordAsync(File("/lib/a.mkv", LibraryFileClassification.Matches, Probe("h264", 1080, ("audio", "aac", 2, "eng"))));

        await _store.WithUnitOfWork(uow => uow.ExecuteAsync("DELETE FROM libraries WHERE id = @id", ("@id", _libraryId)));

        Assert.Equal(0, await Read(uow => uow.CountAsync("SELECT COUNT(*) FROM library_file_facets")));
    }
}
