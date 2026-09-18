using System.Globalization;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Processing;
using Weir.Core.Processing.RemuxPass;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processing.RemuxPass;
using Weir.Infrastructure.Tests.Media;
using Weir.Infrastructure.Tests.MediaManagers;

namespace Weir.Infrastructure.Tests.Processing.RemuxPass;

/// <summary>
/// A library that keeps the original download (<c>remove_original_after_success</c> off, migration 0010): a successful pass
/// leaves the source, its folder and its sidecars in the watched folder, the next scan does not clean the same file again,
/// and a replaced file at the same path is cleaned as new. Real database, folders, scan, handler and worker loop; only
/// ffprobe/ffmpeg are fakes.
/// </summary>
public sealed class KeepOriginalDownloadTests : IDisposable
{
    private readonly MediaManagerFixture _fixture = new();
    private readonly PassFolders _folders = new();
    private readonly FakeMediaRunner _media = new();
    private long _libraryId;

    public KeepOriginalDownloadTests()
    {
        _fixture.Store.Clock.Set(DateTimeOffset.UtcNow);
        _fixture.Store.Execute(
            "UPDATE operator_settings SET min_file_age_seconds = 0, min_input_file_size_mb = 0, minimum_free_disk_space_mb = 0")
            .GetAwaiter().GetResult();
    }

    public void Dispose()
    {
        _folders.Dispose();
        _fixture.Dispose();
    }

    private async Task SetUpAsync(string mediaType, bool removeOriginal)
    {
        await _fixture.Store.Execute("DELETE FROM libraries");
        _libraryId = Convert.ToInt64(await _fixture.Db(uow => uow.ExecuteScalarWriteAsync(
            "INSERT INTO libraries (name, media_type, watched_folder, output_folder, work_folder, failure_policy, max_attempts, " +
            "rejected_file_action, retry_backoff_seconds, min_file_age_seconds, file_detection_interval_seconds, display_order, " +
            "sidecar_patterns_csv, remove_original_after_success) " +
            "VALUES ('Library', $t, $w, $o, $k, 'pass_through', 3, 'leave', 60, 0, 0, 1, '.srt', $remove) RETURNING id",
            ("$t", mediaType),
            ("$w", _folders.Watched),
            ("$o", _folders.Output),
            ("$k", _folders.Work),
            ("$remove", removeOriginal ? 1 : 0))), CultureInfo.InvariantCulture);
        _media.DefaultProbe = FakeMediaRunner.EnglishOnly;
        _media.Probes["Film.2024.mkv"] = FakeMediaRunner.EnglishAndJapanese;
        _media.Probes["Show.S01E01.mkv"] = FakeMediaRunner.EnglishAndJapanese;
    }

    private RemuxPassHandler RemuxHandler()
    {
        var data = new SqliteRemuxPassData(_fixture.Store.Database, _fixture.Connections, NullLogger<SqliteRemuxPassData>.Instance);
        var runner = new RemuxPassRunner(
            new MediaTools(_media, new FixedResolver(), new ListLogger<MediaTools>(), TimeProvider.System),
            new FixedResolver(),
            data,
            data,
            new TvSeasonFolderCleanup(_fixture.Store.Database, _fixture.Connections, TimeProvider.System, NullLogger<TvSeasonFolderCleanup>.Instance),
            new FakeOriginalLanguage(),
            new RemuxPassSettings { WatchedFolderMinFileAgeSeconds = 0 },
            TimeProvider.System,
            NullLogger<RemuxPassRunner>.Instance);
        return new RemuxPassHandler(
            _fixture.Store.Database,
            _fixture.Store.Options,
            runner,
            new QueueingFailurePolicy(_fixture.Jobs),
            TimeProvider.System,
            NullLogger<RemuxPassHandler>.Instance,
            _fixture.Reporter);
    }

    private ProcessingJobProcessor Worker() => new(
        _fixture.Jobs,
        new JobHandlerRegistry([RemuxHandler()]),
        new SqliteActivityWriter(_fixture.Store.Database),
        new NoUnhandledJobFailureRecorder(),
        new NoJobNotifications(),
        _fixture.Store.Clock,
        NullLogger<ProcessingJobProcessor>.Instance);

    private async Task ScanAndDrainAsync(string mediaType)
    {
        var scan = new ProcessingWatchedFolderScanDispatchJobHandler(
            _fixture.Store.Database, _fixture.Store.Clock, _fixture.Store.Options, _fixture.Jobs, _fixture.Connections);
        var payload = new PyDict().Set("enqueue_remux_jobs", true).Set("scan_trigger", "watcher").Set("media_scope", mediaType).Set("library_id", _libraryId);
        var job = await _fixture.Jobs.EnqueueOrGetAsync(
            $"scan-{Guid.NewGuid():N}", ProcessingWatchedFolderScanDispatchJobKinds.ScanDispatch, PyJsonWriter.Dumps(payload, PyJsonFormat.Compact));
        await scan.HandleAsync(new JobWorkContext(job.Id, job.JobKind, job.PayloadJson, "scan-owner"), CancellationToken.None);
        await _fixture.Store.Execute($"UPDATE jobs SET status = 'completed' WHERE id = {job.Id}");

        var worker = Worker();
        for (var i = 0; i < 20; i++)
        {
            if (await worker.ProcessOneAsync("test-worker") == JobProcessOutcome.Idle)
            {
                return;
            }
        }

        Assert.Fail("The worker never went idle.");
    }

    private Task<long> RemuxJobsAsync() =>
        _fixture.Store.Scalar($"SELECT count(*) FROM jobs WHERE job_kind = '{RemuxPassOutcomes.JobKind}'");

    private async Task<string> StatusAsync(string relative)
    {
        using var connection = _fixture.Store.Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = $"SELECT status FROM files WHERE relative_path = '{relative}'";
        return Convert.ToString(await command.ExecuteScalarAsync(), CultureInfo.InvariantCulture) ?? string.Empty;
    }

    [Fact]
    public async Task A_kept_movie_stays_with_its_folder_and_sidecar_and_a_rescan_does_not_clean_it_again()
    {
        await SetUpAsync("movie", removeOriginal: false);
        var source = _folders.Source(Path.Join("Film.2024", "Film.2024.mkv"));
        var sidecar = Path.Join(_folders.Watched, "Film.2024", "Film.2024.en.srt");
        await File.WriteAllTextAsync(sidecar, "1\n00:00:01,000 --> 00:00:02,000\nHi\n");

        await ScanAndDrainAsync("movie");

        Assert.Equal(1, await RemuxJobsAsync());
        Assert.Single(_media.Remuxes);
        Assert.True(File.Exists(source), "the original download must stay where the download client put it");
        Assert.True(File.Exists(sidecar));
        Assert.True(File.Exists(_folders.Out(Path.Join("Film.2024", "Film.2024.mkv"))));
        Assert.True(File.Exists(_folders.Out(Path.Join("Film.2024", "Film.2024.en.srt"))), "sidecars are still copied to the output");
        Assert.Equal("processed", await StatusAsync("Film.2024/Film.2024.mkv"));
        Assert.Equal(new FileInfo(source).Length, await _fixture.Store.Scalar("SELECT processed_source_size FROM files WHERE relative_path = 'Film.2024/Film.2024.mkv'"));

        // Sonarr/Radarr import it and the output goes: the kept original must still not be cleaned again.
        File.Delete(_folders.Out(Path.Join("Film.2024", "Film.2024.mkv")));
        await ScanAndDrainAsync("movie");
        await ScanAndDrainAsync("movie");

        Assert.Equal(1, await RemuxJobsAsync());
        Assert.Single(_media.Remuxes);
        Assert.True(File.Exists(source));
        Assert.Equal("processed", await StatusAsync("Film.2024/Film.2024.mkv"));
    }

    [Fact]
    public async Task A_replaced_file_at_the_same_path_is_cleaned_as_new_even_at_the_same_size()
    {
        await SetUpAsync("movie", removeOriginal: false);
        var source = _folders.Source(Path.Join("Film.2024", "Film.2024.mkv"));
        await ScanAndDrainAsync("movie");
        Assert.Equal(1, await RemuxJobsAsync());

        // The same release grabbed again: same path, same size, a later modification time.
        File.WriteAllBytes(source, Enumerable.Repeat((byte)'y', 2000).ToArray());
        File.SetLastWriteTimeUtc(source, DateTime.UtcNow.AddMinutes(5));
        await ScanAndDrainAsync("movie");

        Assert.Equal(2, await RemuxJobsAsync());
        Assert.Equal(2, _media.Remuxes.Count());
        Assert.Equal("processed", await StatusAsync("Film.2024/Film.2024.mkv"));
        Assert.True(File.Exists(source));
    }

    [Fact]
    public async Task A_kept_tv_episode_leaves_its_season_folder_and_is_not_cleaned_again()
    {
        await SetUpAsync("tv", removeOriginal: false);
        var episode = _folders.Source(Path.Join("Show.S01", "Show.S01E01.mkv"));

        await ScanAndDrainAsync("tv");
        await ScanAndDrainAsync("tv");

        Assert.Equal(1, await RemuxJobsAsync());
        Assert.True(File.Exists(episode));
        Assert.True(File.Exists(_folders.Out(Path.Join("Show.S01", "Show.S01E01.mkv"))));
        Assert.Contains(
            RemuxPassRunner.KeptOriginalReason,
            await ActivityDetailAsync(),
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task By_default_the_original_is_still_removed_after_a_successful_pass()
    {
        await SetUpAsync("movie", removeOriginal: true);
        var source = _folders.Source(Path.Join("Film.2024", "Film.2024.mkv"));
        File.SetLastWriteTimeUtc(source, DateTime.UtcNow.AddDays(-3));

        await ScanAndDrainAsync("movie");

        Assert.Equal(1, await RemuxJobsAsync());
        Assert.False(Directory.Exists(Path.Join(_folders.Watched, "Film.2024")), "removing the original stays the default");
    }

    [Fact]
    public void The_fingerprint_rule_needs_the_same_size_and_time_on_a_processed_row()
    {
        var row = new ProcessingFileRecord
        {
            RelativePath = "a.mkv",
            Status = ProcessingFileStatuses.Processed,
            ProcessedSourceSize = 2000,
            ProcessedSourceMtimeNs = 1_700_000_000_000_000_000,
        };

        Assert.True(ProcessedSourceRules.IsSameCleanedFile(row, 2000, 1_700_000_000_000_000_000));
        Assert.False(ProcessedSourceRules.IsSameCleanedFile(row, 2001, 1_700_000_000_000_000_000));
        Assert.False(ProcessedSourceRules.IsSameCleanedFile(row, 2000, 1_700_000_000_000_000_001));
        Assert.False(ProcessedSourceRules.IsSameCleanedFile(row with { Status = ProcessingFileStatuses.ProcessingFailed }, 2000, 1_700_000_000_000_000_000));
        Assert.False(ProcessedSourceRules.IsSameCleanedFile(row with { ProcessedSourceMtimeNs = null }, 2000, 1_700_000_000_000_000_000));
        Assert.False(ProcessedSourceRules.IsSameCleanedFile(null, 2000, 1));
    }

    private async Task<string> ActivityDetailAsync()
    {
        using var connection = _fixture.Store.Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT group_concat(detail, '\n') FROM activity_events WHERE event_type = 'processing.file_remux_pass_completed'";
        return Convert.ToString(await command.ExecuteScalarAsync(), CultureInfo.InvariantCulture) ?? string.Empty;
    }
}
