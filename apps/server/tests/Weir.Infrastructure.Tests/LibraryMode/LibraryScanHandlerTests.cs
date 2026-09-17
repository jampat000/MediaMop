using System.Globalization;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Tests.Media;
using Weir.Infrastructure.Tests.MediaManagers;
using Weir.Infrastructure.Tests.Refiner.RemuxPass;

namespace Weir.Infrastructure.Tests.LibraryMode;

/// <summary>
/// #505 point 2: the scan job walks library folders, probes (cached by path/size/mtime), classifies with the library's
/// rules, and never writes to a file it looked at.
/// </summary>
public sealed class LibraryScanHandlerTests : IDisposable
{
    private readonly MediaManagerFixture _fixture = new();
    private readonly TempDirectory _libraryFolder = new();
    private readonly FakeMediaRunner _media = new();

    public void Dispose()
    {
        _libraryFolder.Dispose();
        _fixture.Dispose();
    }

    private LibraryScanHandler Handler() => new(
        _fixture.Store.Database,
        new MediaTools(_media, new FixedResolver(), new ListLogger<MediaTools>(), TimeProvider.System),
        _fixture.Store.Clock,
        NullLogger<LibraryScanHandler>.Instance);

    private async Task<long> LibraryAsync() =>
        Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO refiner_libraries (name, media_type, watched_folder, output_folder, work_folder, display_order) " +
            "VALUES ('Movies library', 'movie', '/downloads/watched', '/downloads/output', '/downloads/work', 1) RETURNING id")), CultureInfo.InvariantCulture);

    private Task<long> EnqueueScanAsync(long libraryId) =>
        _fixture.Store.WithUnitOfWork(async uow => (await LibraryScanStore.RequestScanAsync(uow, _fixture.Jobs, libraryId, "manual")).Id);

    /// <summary>Claims, runs and completes one scan job exactly as the real worker would, so its row ends up
    /// <c>completed</c> — <see cref="LibraryScanStore.LatestSnapshotAsync"/> only reads a completed row.</summary>
    private async Task RunScanAsync(long jobId)
    {
        const string leaseOwner = "test-worker";
        var claimed = await _fixture.Jobs.ClaimNextAsync(leaseOwner, _fixture.Store.Clock.GetUtcNow().AddMinutes(5), _fixture.Store.Clock.GetUtcNow());
        Assert.NotNull(claimed);
        Assert.Equal(jobId, claimed!.Id);
        await Handler().HandleAsync(new JobWorkContext(claimed.Id, claimed.JobKind, claimed.PayloadJson, leaseOwner), CancellationToken.None);
        Assert.True(await _fixture.Jobs.CompleteClaimedAsync(claimed.Id, leaseOwner));
    }

    [Fact]
    public async Task A_scan_classifies_files_and_writes_nothing_to_them()
    {
        var library = await LibraryAsync();
        await _fixture.Db(async uow => { await LibrarySettingsStore.SetAsync(uow, library, new LibrarySettings([_libraryFolder.Path], false)); return true; });

        var matchingPath = _libraryFolder.Join("english-only.mkv");
        var changingPath = _libraryFolder.Join("english-and-japanese.mkv");
        await File.WriteAllBytesAsync(matchingPath, [1, 2, 3]);
        await File.WriteAllBytesAsync(changingPath, [4, 5, 6]);
        _media.Probes["english-only.mkv"] = FakeMediaRunner.EnglishOnly;
        _media.Probes["english-and-japanese.mkv"] = FakeMediaRunner.EnglishAndJapanese;
        var matchingBytesBefore = File.ReadAllBytes(matchingPath);
        var matchingWriteTimeBefore = File.GetLastWriteTimeUtc(matchingPath);
        var changingBytesBefore = File.ReadAllBytes(changingPath);
        var changingWriteTimeBefore = File.GetLastWriteTimeUtc(changingPath);

        var jobId = await EnqueueScanAsync(library);
        await RunScanAsync(jobId);

        // Never writes: content and mtime of every scanned file are exactly as before.
        Assert.Equal(matchingBytesBefore, File.ReadAllBytes(matchingPath));
        Assert.Equal(matchingWriteTimeBefore, File.GetLastWriteTimeUtc(matchingPath));
        Assert.Equal(changingBytesBefore, File.ReadAllBytes(changingPath));
        Assert.Equal(changingWriteTimeBefore, File.GetLastWriteTimeUtc(changingPath));

        var snapshot = await _fixture.Db(uow => LibraryScanStore.LatestSnapshotAsync(uow, library), commit: false);
        Assert.NotNull(snapshot);
        Assert.Equal(2, snapshot!.Files.Count);
        var matching = snapshot.Files.Single(f => f.Path == matchingPath);
        var changing = snapshot.Files.Single(f => f.Path == changingPath);
        Assert.Equal(LibraryFileClassification.Matches, matching.Classification);
        Assert.Equal(LibraryFileClassification.WouldChange, changing.Classification);
        Assert.Equal(1, changing.RemovedAudioCount);

        // Unmatched (no manager linked to this library): still processable, not skipped.
        Assert.Null(changing.ManagerKind);
        Assert.Null(changing.ManagerTitle);
    }

    [Fact]
    public async Task A_second_scan_reuses_the_cached_probe_for_an_unchanged_file()
    {
        var library = await LibraryAsync();
        await _fixture.Db(async uow => { await LibrarySettingsStore.SetAsync(uow, library, new LibrarySettings([_libraryFolder.Path], false)); return true; });
        var path = _libraryFolder.Join("film.mkv");
        await File.WriteAllBytesAsync(path, [1, 2, 3]);
        _media.Probes["film.mkv"] = FakeMediaRunner.EnglishOnly;

        var firstJobId = await EnqueueScanAsync(library);
        await RunScanAsync(firstJobId);
        var probesAfterFirst = _media.Probed.Count();
        Assert.True(probesAfterFirst > 0);

        var secondJobId = await EnqueueScanAsync(library);
        await RunScanAsync(secondJobId);

        // The file's size and mtime have not changed, so the cached ffprobe answer is reused: no new probe call.
        Assert.Equal(probesAfterFirst, _media.Probed.Count());
    }

    [Fact]
    public async Task Scanning_a_library_with_no_folders_configured_reports_a_reason_and_probes_nothing()
    {
        var library = await LibraryAsync();
        var jobId = await EnqueueScanAsync(library);
        await RunScanAsync(jobId);

        Assert.Empty(_media.Probed);
        var snapshot = await _fixture.Db(uow => LibraryScanStore.LatestSnapshotAsync(uow, library), commit: false);
        Assert.NotNull(snapshot);
        Assert.Empty(snapshot!.Files);
    }
}
