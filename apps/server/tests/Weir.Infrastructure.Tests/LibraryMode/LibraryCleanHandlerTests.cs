using System.Globalization;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Core.LibraryMode;
using Weir.Core.Refiner.RemuxPass;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Tests.Media;
using Weir.Infrastructure.Tests.MediaManagers;
using Weir.Infrastructure.Tests.Refiner.RemuxPass;

namespace Weir.Infrastructure.Tests.LibraryMode;

/// <summary>
/// #505 point 8: the clean job plans exactly as the scan did, then remuxes to a temp file beside the original and hands it
/// to the #506 safe swap. Refuses removal without confirmation, never touches the failure policy, and sorts behind
/// download-pipeline jobs.
/// </summary>
public sealed class LibraryCleanHandlerTests : IDisposable
{
    private readonly MediaManagerFixture _fixture = new();
    private readonly TempDirectory _libraryFolder = new();
    private readonly FakeMediaRunner _media = new();

    public void Dispose()
    {
        _libraryFolder.Dispose();
        _fixture.Dispose();
    }

    private LibraryCleanHandler Handler()
    {
        var tools = new MediaTools(_media, new FixedResolver(), new ListLogger<MediaTools>(), TimeProvider.System);
        var swap = new SafeSwap(
            PhysicalSwapFileSystem.Instance,
            new RefinerJobSwapJournal(_fixture.Store.Database),
            new RemuxOutputSwapValidator(tools, NullLogger<RemuxOutputSwapValidator>.Instance),
            NullLogger<SafeSwap>.Instance);
        // No manager connections are configured in this fixture, so the real notifier finds nothing that owns
        // the changed path and makes no HTTP call — equivalent to a no-op for these tests, but exercising the
        // same #507 code the running server does.
        var notifier = new LibraryFileChangeNotifier(
            _fixture.Connections, _fixture.Store.Database, new SqliteActivityWriter(_fixture.Store.Database), _fixture.Store.Clock, delay: (_, _) => Task.CompletedTask);
        var removedTrackStore = new Weir.Infrastructure.Library.FileLogRemovedTrackStore(_fixture.Store.Database, _fixture.Store.Clock);
        return new LibraryCleanHandler(_fixture.Store.Database, tools, swap, notifier, PhysicalHardlinkInspector.Instance, removedTrackStore, _fixture.Store.Clock, NullLogger<LibraryCleanHandler>.Instance);
    }

    /// <summary>A library whose rule set keeps only English audio, strictly — the same policy proven in
    /// <c>LibraryFilePlannerTests</c> to drop a Japanese track.</summary>
    private async Task<long> LibraryAsync()
    {
        var ruleSetId = Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO refiner_rule_sets (name, primary_audio_lang, audio_preference_mode) " +
            "VALUES ('English only', 'eng', 'preferred_langs_strict') RETURNING id")), CultureInfo.InvariantCulture);
        return Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO refiner_libraries (name, media_type, watched_folder, output_folder, work_folder, display_order, rule_set_id) " +
            "VALUES ('Movies library', 'movie', '/downloads/watched', '/downloads/output', '/downloads/work', 1, $rule_set_id) RETURNING id",
            ("$rule_set_id", ruleSetId))), CultureInfo.InvariantCulture);
    }

    private Task<long> EnqueueCleanAsync(long libraryId, string path, bool confirmFinalRemoval) =>
        _fixture.Store.WithUnitOfWork(async uow =>
            (await LibraryScanStore.EnqueueCleanAsync(uow, _fixture.Jobs, libraryId, path, "manual", confirmFinalRemoval)).Id);

    /// <summary>Claims, runs and completes one clean job exactly as the real worker would.</summary>
    private async Task RunCleanAsync(long jobId)
    {
        const string leaseOwner = "test-worker";
        var claimed = await _fixture.Jobs.ClaimNextAsync(leaseOwner, _fixture.Store.Clock.GetUtcNow().AddMinutes(5), _fixture.Store.Clock.GetUtcNow());
        Assert.NotNull(claimed);
        Assert.Equal(jobId, claimed!.Id);
        await Handler().HandleAsync(new JobWorkContext(claimed.Id, claimed.JobKind, claimed.PayloadJson, leaseOwner), CancellationToken.None);
        await _fixture.Jobs.CompleteClaimedAsync(claimed.Id, leaseOwner);
    }

    private Task<int> ReferencePolicyJobCountAsync() =>
        _fixture.Store.Scalar(
                $"SELECT count(*) FROM refiner_jobs WHERE job_kind IN ('refiner.file.reject.v1', 'refiner.file.pass_through.v1')")
            .ContinueWith(t => (int)t.Result, TaskScheduler.Default);

    [Fact]
    public async Task Cleaning_a_file_that_would_remove_tracks_is_refused_without_confirmation()
    {
        var library = await LibraryAsync();
        var path = _libraryFolder.Join("film.mkv");
        await File.WriteAllBytesAsync(path, [1, 2, 3]);
        _media.Probes["film.mkv"] = FakeMediaRunner.EnglishAndJapanese;
        var before = await File.ReadAllBytesAsync(path);

        var jobId = await EnqueueCleanAsync(library, path, confirmFinalRemoval: false);
        await RunCleanAsync(jobId);

        // Refused: the original is untouched, and only Activity's "failed" event was written — no swap ran.
        Assert.Equal(before, await File.ReadAllBytesAsync(path));
        Assert.False(File.Exists(SafeSwapRules.TempPath(path)));
        Assert.False(File.Exists(SafeSwapRules.BackupPath(path)));
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM activity_events WHERE event_type = '{LibraryActivityEventTypes.FileFailed}'"));
    }

    [Fact]
    public async Task A_library_failure_never_queues_a_reject_or_pass_through_job()
    {
        var library = await LibraryAsync();
        var path = _libraryFolder.Join("unreadable.mkv");
        await File.WriteAllBytesAsync(path, [9, 9, 9]);
        _media.ProbeError = "moov atom not found";

        var jobId = await EnqueueCleanAsync(library, path, confirmFinalRemoval: true);
        await RunCleanAsync(jobId);

        Assert.Equal(0, await ReferencePolicyJobCountAsync());
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM activity_events WHERE event_type = '{LibraryActivityEventTypes.FileFailed}'"));
    }

    [Fact]
    public async Task Library_jobs_are_claimed_behind_a_pending_download_job()
    {
        var library = await LibraryAsync();
        var path = _libraryFolder.Join("film.mkv");
        await File.WriteAllBytesAsync(path, [1, 2, 3]);

        // A library job enqueued first, then a download job enqueued after: priority still decides, not order.
        await EnqueueCleanAsync(library, path, confirmFinalRemoval: true);
        await _fixture.Jobs.EnqueueOrGetAsync("download:1", RemuxPassOutcomes.JobKind, "{}");

        var first = await _fixture.Jobs.ClaimNextAsync("w1", _fixture.Store.Clock.GetUtcNow().AddMinutes(5), _fixture.Store.Clock.GetUtcNow());
        Assert.NotNull(first);
        Assert.Equal(RemuxPassOutcomes.JobKind, first!.JobKind);

        var second = await _fixture.Jobs.ClaimNextAsync("w2", _fixture.Store.Clock.GetUtcNow().AddMinutes(5), _fixture.Store.Clock.GetUtcNow());
        Assert.NotNull(second);
        Assert.Equal(LibraryModeJobKinds.CleanKind, second!.JobKind);
    }

    [Fact]
    public async Task A_file_with_no_matching_manager_still_processes()
    {
        // No manager connections are linked to the library, so the file is unmatched — #505 says that must not block it.
        var library = await LibraryAsync();
        var path = _libraryFolder.Join("film.mkv");
        await File.WriteAllBytesAsync(path, [1, 2, 3]);
        _media.Probes["film.mkv"] = FakeMediaRunner.EnglishAndJapanese;

        var jobId = await EnqueueCleanAsync(library, path, confirmFinalRemoval: true);
        await RunCleanAsync(jobId);

        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM activity_events WHERE event_type = '{LibraryActivityEventTypes.FileCleaned}'"));
        Assert.False(File.Exists(path + ".weir-bak.mkv"));
    }

    [Fact]
    public async Task An_end_to_end_clean_replaces_the_file_in_place_and_leaves_no_leftovers()
    {
        var library = await LibraryAsync();
        var path = _libraryFolder.Join("film.mkv");
        var originalBytes = new byte[] { 0xAA, 0xBB, 0xCC, 0xDD };
        await File.WriteAllBytesAsync(path, originalBytes);
        _media.Probes["film.mkv"] = FakeMediaRunner.EnglishAndJapanese;

        var jobId = await EnqueueCleanAsync(library, path, confirmFinalRemoval: true);
        await RunCleanAsync(jobId);

        // Committed: the file at the original name now holds the cleaned (fake) output, and no temp/backup remains.
        Assert.True(File.Exists(path));
        Assert.NotEqual(originalBytes, await File.ReadAllBytesAsync(path));
        Assert.False(File.Exists(SafeSwapRules.TempPath(path)));
        Assert.False(File.Exists(SafeSwapRules.BackupPath(path)));
        Assert.Equal(1, await _fixture.Store.Scalar($"SELECT count(*) FROM activity_events WHERE event_type = '{LibraryActivityEventTypes.FileCleaned}'"));
        Assert.Equal(0, await ReferencePolicyJobCountAsync());
    }
}
