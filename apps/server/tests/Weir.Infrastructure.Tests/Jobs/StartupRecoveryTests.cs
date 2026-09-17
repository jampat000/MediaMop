using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>
/// Ports of <c>test_startup_crash_recovery.py</c>, and the #534 fix: a crash leaves Weir's remux temp
/// output in the work folder, and recovery removes it without touching anything else.
/// </summary>
public sealed class StartupRecoveryTests : IDisposable
{
    private static readonly DateTimeOffset Now = new(2026, 4, 29, 12, 0, 0, TimeSpan.Zero);
    private readonly JobsTestDatabase _db = new();

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task Startup_recovery_requeues_leased_jobs_with_attempts_remaining()
    {
        _db.InsertRawJob("refiner-recover", "refiner.test.v1", RefinerJobStatus.Leased, "dead-refiner", "2026-04-29 13:00:00+00:00", attemptCount: 1, maxAttempts: 3);

        var report = await RunAsync();

        Assert.Equal(new StartupJobRecoveryResult(1, 0), report.Jobs);
        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal("pending", row.Status);
        Assert.Null(row.LeaseOwner);
        Assert.Null(row.LeaseExpiresAt);
        Assert.Equal(
            "This job was interrupted by a Weir restart. Recovered at 2026-04-29T12:00:00+00:00 and queued for another safe attempt.",
            row.LastError);
        // Claimable straight away, not after the dead lease would have expired.
        Assert.NotNull(await _db.Store.ClaimNextAsync("w", Now.AddHours(1), Now));
    }

    [Fact]
    public async Task Startup_recovery_fails_leased_jobs_after_final_attempt()
    {
        _db.InsertRawJob("refiner-final", "refiner.test.v1", RefinerJobStatus.Leased, "dead-refiner", "2026-04-29 13:00:00+00:00", attemptCount: 3, maxAttempts: 3);

        var report = await RunAsync();

        Assert.Equal(new StartupJobRecoveryResult(0, 1), report.Jobs);
        var row = (await _db.Store.GetAsync(1))!;
        Assert.Equal(RefinerJobStatus.Failed, row.Status);
        Assert.Null(row.LeaseOwner);
        Assert.Null(row.LeaseExpiresAt);
        Assert.Contains("marked failed", row.LastError, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Startup_recovery_leaves_rows_that_were_not_leased_alone()
    {
        _db.InsertRawJob("pending", "refiner.test.v1");
        _db.InsertRawJob("done", "refiner.test.v1", RefinerJobStatus.Completed);

        var report = await RunAsync();

        Assert.Equal(0, report.Jobs.TotalRecovered);
        Assert.Equal(0, _db.Count("SELECT count(*) FROM refiner_jobs WHERE last_error IS NOT NULL"));
    }

    [Fact]
    public async Task Startup_refiner_recovery_removes_hidden_partial_outputs()
    {
        var output = _db.Join("output");
        var nested = Path.Join(output, "Movie");
        Directory.CreateDirectory(nested);
        var partial = Path.Join(nested, ".movie.mkv.abc.partial");
        await File.WriteAllTextAsync(partial, "partial");
        var final = Path.Join(nested, "movie.mkv");
        await File.WriteAllTextAsync(final, "complete");
        var visible = Path.Join(nested, "movie.partial");
        await File.WriteAllTextAsync(visible, "not hidden");
        _db.AddLibrary(outputFolder: output);

        var report = await RunAsync();

        Assert.Equal(1, report.PartialOutputsRemoved);
        Assert.False(File.Exists(partial));
        Assert.Equal("complete", await File.ReadAllTextAsync(final));
        Assert.True(File.Exists(visible));
    }

    [Fact]
    public async Task Partial_outputs_under_the_default_output_root_are_removed_with_no_libraries()
    {
        var root = Path.Join(_db.Home, "refiner-output", "x");
        Directory.CreateDirectory(root);
        var partial = Path.Join(root, ".a.mkv.q1.partial");
        await File.WriteAllTextAsync(partial, "p");

        Assert.Equal(1, (await RunAsync()).PartialOutputsRemoved);
        Assert.False(File.Exists(partial));
    }

    [Fact]
    public async Task A_crash_mid_remux_leaves_no_temp_output_in_the_custom_work_folder_534()
    {
        var work = _db.Join("work-movies");
        Directory.CreateDirectory(work);
        var library = _db.AddLibrary(workFolder: work, outputFolder: _db.Join("out"));
        _db.InsertRawJob(
            "refiner.file.remux_pass:film",
            "refiner.file.remux_pass.v1",
            RefinerJobStatus.Leased,
            "dead",
            "2026-04-29 13:00:00+00:00",
            attemptCount: 1,
            payloadJson: $"{{\"library_id\": {library}, \"media_scope\": \"movie\", \"relative_media_path\": \"Film (2020)/Film (2020).mkv\"}}");
        var temp = Path.Join(work, "Film (2020).refiner.k3j_9x2a.mkv");
        await File.WriteAllTextAsync(temp, "half-written remux");
        string[] keep =
        [
            Path.Join(work, "Film (2020).mkv"),
            Path.Join(work, "Film (2020).refiner.notes.txt"),
            Path.Join(work, "Film (2020).refiner.ZZZZZZZZ.mkv"),
            Path.Join(work, "Other.refiner.k3j_9x2a"),
            Path.Join(work, "readme.txt"),
        ];
        foreach (var path in keep)
        {
            await File.WriteAllTextAsync(path, "operator file");
        }

        Directory.CreateDirectory(Path.Join(work, "nested"));
        var nested = Path.Join(work, "nested", "Film (2020).refiner.k3j_9x2a.mkv");
        await File.WriteAllTextAsync(nested, "not where Weir writes temp output");

        var report = await RunAsync();

        Assert.Equal(1, report.Jobs.RefinerRequeued);
        Assert.Equal(1, report.WorkTempFilesRemoved);
        Assert.False(File.Exists(temp));
        Assert.All(keep, path => Assert.True(File.Exists(path), path));
        Assert.True(File.Exists(nested));
    }

    [Fact]
    public async Task Interrupted_job_temp_output_is_found_in_the_default_work_folder_for_its_scope()
    {
        // Seeded libraries with no work folder use WEIR_HOME/refiner/refiner-{movie,tv}-work.
        var tvWork = Path.Join(_db.Home, "refiner", "refiner-tv-work");
        Directory.CreateDirectory(tvWork);
        _db.InsertRawJob(
            "tv",
            "refiner.file.remux_pass.v1",
            RefinerJobStatus.Leased,
            "dead",
            "2026-04-29 13:00:00+00:00",
            attemptCount: 3,
            payloadJson: "{\"media_scope\": \"tv\", \"relative_media_path\": \"Show/S01/Show.S01E01\"}");
        var temp = Path.Join(tvWork, "Show.S01E01.refiner.abcdefgh.mkv");
        await File.WriteAllTextAsync(temp, "x");

        var report = await RunAsync();

        Assert.Equal(1, report.Jobs.RefinerFailed);
        Assert.Equal(1, report.WorkTempFilesRemoved);
        Assert.False(File.Exists(temp));
    }

    [Fact]
    public async Task The_startup_sweep_removes_only_weir_temp_names_from_every_work_folder()
    {
        var custom = _db.Join("custom-work");
        Directory.CreateDirectory(custom);
        _db.AddLibrary(name: "Custom", workFolder: custom);
        var movieDefault = Path.Join(_db.Home, "refiner", "refiner-movie-work");
        Directory.CreateDirectory(movieDefault);
        string[] weirTemps =
        [
            Path.Join(custom, "a.refiner.aaaaaaaa.mkv"),
            Path.Join(custom, "dry-run-ffmpeg-destination-placeholder.mkv"),
            Path.Join(movieDefault, "b.c.refiner.12345678.mp4"),
        ];
        string[] others =
        [
            Path.Join(custom, "a.refiner.mkv"),
            Path.Join(custom, "a.mkv"),
            Path.Join(custom, ".a.mkv.x.work-preflight"),
            Path.Join(movieDefault, "planned-ffmpeg-destination-placeholder.mkv"),
            Path.Join(movieDefault, "b.refiner.1234567.mp4"),
        ];
        foreach (var path in weirTemps.Concat(others))
        {
            await File.WriteAllTextAsync(path, "x");
        }

        var report = await RunAsync();

        Assert.Equal(weirTemps.Length, report.WorkTempFilesRemoved);
        Assert.All(weirTemps, path => Assert.False(File.Exists(path), path));
        Assert.All(others, path => Assert.True(File.Exists(path), path));
    }

    [Fact]
    public async Task Missing_work_and_output_folders_are_not_an_error()
    {
        _db.AddLibrary(workFolder: _db.Join("does-not-exist"), outputFolder: _db.Join("nor-this"));

        var report = await RunAsync();

        Assert.Equal(new StartupRecoveryReport(new StartupJobRecoveryResult(0, 0), 0, 0), report);
    }

    [Fact]
    public void A_legacy_default_work_folder_resolves_to_the_scope_default()
    {
        var legacy = new RefinerLibraryFolderRow(1, "movie", 0, @"C:\ProgramData\Media\refiner-movie-work\", string.Empty);

        Assert.Equal(RefinerLibraryFolders.DefaultMovieWorkFolder(_db.Home), RefinerLibraryFolders.EffectiveWorkFolder(legacy, _db.Home));
        Assert.Equal(RefinerLibraryFolders.DefaultTvWorkFolder(_db.Home), RefinerLibraryFolders.EffectiveWorkFolder(legacy with { MediaType = "TV", WorkFolder = " " }, _db.Home));
        Assert.Equal("/data/work", RefinerLibraryFolders.EffectiveWorkFolder(legacy with { WorkFolder = " /data/work " }, _db.Home));
    }

    private Task<StartupRecoveryReport> RunAsync() => StartupRecovery.RunAsync(_db.Store, _db.Home, Now, NullLogger.Instance);
}
