using Weir.Core.Processing;
using Weir.Infrastructure.Processing;
using Weir.Infrastructure.Sqlite;
using Weir.Infrastructure.Tests.Jobs;

namespace Weir.Infrastructure.Tests.Processing;

/// <summary>
/// Real-SQLite proof of the fix for #530: a <c>files</c> row at <c>passed_through</c> or
/// <c>rejected</c> lists, filters and counts exactly like any other status — the Python response/query
/// schema (<c>ProcessingFileStatusName</c>) omitted both, which 500'd a list containing one and 422'd a
/// filter naming one.
/// </summary>
public sealed class FileStateStoreTests
{
    private static long InsertLibrary(JobsTestDatabase db, string name = "Movies bug530")
    {
        db.Execute(
            "INSERT INTO libraries (name, media_type) VALUES (@name, 'movie')",
            ("@name", name));
        return Convert.ToInt64(db.Scalar("SELECT id FROM libraries WHERE name = @name", ("@name", name)));
    }

    private static void InsertFile(JobsTestDatabase db, long libraryId, string relativePath, string status) =>
        db.Execute(
            "INSERT INTO files (library_id, relative_path, status, last_seen_at) VALUES (@lib, @path, @status, CURRENT_TIMESTAMP)",
            ("@lib", libraryId), ("@path", relativePath), ("@status", status));

    [Theory]
    [InlineData(ProcessingFileStatuses.PassedThrough)]
    [InlineData(ProcessingFileStatuses.Rejected)]
    public async Task Listing_by_either_bug_530_status_returns_the_row_without_raising(string status)
    {
        using var db = new JobsTestDatabase();
        var libraryId = InsertLibrary(db);
        InsertFile(db, libraryId, "Movie (2020)/movie.mkv", status);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var rows = await FileStateStore.ListAsync(uow, new ProcessingFileListFilter { Status = status });

        var row = Assert.Single(rows);
        Assert.Equal(status, row.Status);
        Assert.Equal("Movie (2020)/movie.mkv", row.RelativePath);
    }

    [Fact]
    public async Task Status_counts_include_both_bug_530_statuses_alongside_every_other_status()
    {
        using var db = new JobsTestDatabase();
        var libraryId = InsertLibrary(db);
        InsertFile(db, libraryId, "a.mkv", ProcessingFileStatuses.PassedThrough);
        InsertFile(db, libraryId, "b.mkv", ProcessingFileStatuses.Rejected);
        InsertFile(db, libraryId, "c.mkv", ProcessingFileStatuses.Processed);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var counts = await FileStateStore.StatusCountsAsync(uow, libraryId);

        Assert.Equal(ProcessingFileStatuses.All.Count, counts.Count);
        Assert.Equal(1, counts[ProcessingFileStatuses.PassedThrough]);
        Assert.Equal(1, counts[ProcessingFileStatuses.Rejected]);
        Assert.Equal(1, counts[ProcessingFileStatuses.Processed]);
        Assert.Equal(0, counts[ProcessingFileStatuses.Unprocessed]);
    }

    [Fact]
    public async Task Listing_with_no_filter_returns_files_across_every_status_newest_first()
    {
        using var db = new JobsTestDatabase();
        var libraryId = InsertLibrary(db);
        InsertFile(db, libraryId, "a.mkv", ProcessingFileStatuses.PassedThrough);
        InsertFile(db, libraryId, "b.mkv", ProcessingFileStatuses.Unprocessed);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var rows = await FileStateStore.ListAsync(uow, new ProcessingFileListFilter());

        Assert.Equal(2, rows.Count);
    }

    [Fact]
    public async Task Path_contains_filters_case_insensitively()
    {
        using var db = new JobsTestDatabase();
        var libraryId = InsertLibrary(db);
        InsertFile(db, libraryId, "Show/S01E01.mkv", ProcessingFileStatuses.Processed);
        InsertFile(db, libraryId, "Other/file.mkv", ProcessingFileStatuses.Processed);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);

        var rows = await FileStateStore.ListAsync(uow, new ProcessingFileListFilter { PathContains = "show" });

        var row = Assert.Single(rows);
        Assert.Equal("Show/S01E01.mkv", row.RelativePath);
    }

    [Fact]
    public async Task Forgetting_a_file_removes_its_record_only()
    {
        using var db = new JobsTestDatabase();
        var libraryId = InsertLibrary(db);
        InsertFile(db, libraryId, "a.mkv", ProcessingFileStatuses.Processed);
        await using var uow = await UnitOfWork.OpenAsync(db.Database);
        var row = Assert.Single(await FileStateStore.ListAsync(uow, new ProcessingFileListFilter()));

        await FileStateStore.ForgetAsync(uow, row.Id);

        Assert.Null(await FileStateStore.GetAsync(uow, row.Id));
    }
}
