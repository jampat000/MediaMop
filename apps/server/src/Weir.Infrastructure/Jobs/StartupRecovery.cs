using System.Globalization;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using Weir.Core.Jobs;

namespace Weir.Infrastructure.Jobs;

/// <summary>What startup recovery found and removed.</summary>
public sealed record StartupRecoveryReport(StartupJobRecoveryResult Jobs, int PartialOutputsRemoved, int WorkTempFilesRemoved);

/// <summary>A job that was leased when the previous process stopped.</summary>
public sealed record InterruptedJob(long Id, string JobKind, string? PayloadJson);

/// <summary>
/// Startup crash recovery: ports of <c>recover_incomplete_jobs_after_startup</c> and
/// <c>cleanup_refiner_partial_output_files</c>, plus the #534 fix for remux temp output left in work folders.
/// </summary>
/// <remarks>
/// Startup is a hard process boundary for this single-node app: no worker is running yet, so a leased
/// row belongs to a dead worker, and a Weir temp file belongs to interrupted work.
/// <para>
/// #534: Python removed only hidden <c>.partial</c> files from output folders, leaving a crashed
/// remux's multi-gigabyte temp output in the work folder forever. Here recovery also removes (1) the
/// remux temp output of every job that was in progress, found from its payload's library and file, and
/// (2) any other remux temp output in a library work folder. Both only ever match the exact names Weir
/// creates (<see cref="WeirTempFiles"/>), never other files, and only at the top of the work folder,
/// where Weir writes them.
/// </para>
/// </remarks>
public static class StartupRecovery
{
    public static async Task<StartupRecoveryReport> RunAsync(
        RefinerJobStore queue,
        string weirHome,
        DateTimeOffset now,
        ILogger logger,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(queue);
        ArgumentNullException.ThrowIfNull(logger);
        var (result, interrupted, libraries) = await queue.InTransactionAsync(
            (connection, transaction) =>
            {
                var (jobs, rows) = RecoverIncompleteJobs(connection, transaction, now);
                return (jobs, rows, RefinerLibraryFolders.List(connection, transaction));
            },
            cancellationToken).ConfigureAwait(false);

        var tempRemoved = RemoveInterruptedRemuxTempFiles(interrupted, libraries, weirHome, logger);
        tempRemoved += SweepWorkFolderTempFiles(libraries, weirHome, logger);
        var partialRemoved = CleanupPartialOutputFiles(libraries, weirHome);

        if (result.TotalRecovered > 0 || partialRemoved > 0 || tempRemoved > 0)
        {
            logger.LogWarning(
                "Weir startup recovered interrupted work recovered_jobs={RecoveredJobs} partial_outputs_removed={PartialOutputsRemoved} work_temp_files_removed={WorkTempFilesRemoved}",
                $"{{'refiner_requeued': {result.RefinerRequeued}, 'refiner_failed': {result.RefinerFailed}}}",
                partialRemoved,
                tempRemoved);
        }

        return new StartupRecoveryReport(result, partialRemoved, tempRemoved);
    }

    /// <summary><c>recover_incomplete_jobs_after_startup</c> inside the caller's transaction.</summary>
    public static (StartupJobRecoveryResult Result, List<InterruptedJob> Interrupted) RecoverIncompleteJobs(
        SqliteConnection connection,
        SqliteTransaction transaction,
        DateTimeOffset now)
    {
        var when = JobQueueRules.ToMicroseconds(now.ToUniversalTime());
        var requeued = 0;
        var failed = 0;
        var interrupted = new List<InterruptedJob>();
        var rows = RefinerJobStore.Query(
            connection,
            transaction,
            "SELECT id, dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at, attempt_count, max_attempts, " +
            "last_error, not_before, runner_cost, priority, created_at, updated_at FROM refiner_jobs WHERE status = @leased",
            ("@leased", RefinerJobStatus.Leased));
        foreach (var row in rows)
        {
            var decision = StartupJobRecovery.Decide(row.AttemptCount, row.MaxAttempts, when);
            RefinerJobStore.Execute(
                connection,
                transaction,
                "UPDATE refiner_jobs SET lease_owner = NULL, lease_expires_at = NULL, status = @status, last_error = @error, " +
                "updated_at = CURRENT_TIMESTAMP WHERE id = @id",
                ("@status", decision.Status),
                ("@error", decision.LastError),
                ("@id", row.Id));
            if (decision.Requeued)
            {
                requeued++;
            }
            else
            {
                failed++;
            }

            interrupted.Add(new InterruptedJob(row.Id, row.JobKind, row.PayloadJson));
        }

        return (new StartupJobRecoveryResult(requeued, failed), interrupted);
    }

    /// <summary>
    /// #534: remove the remux temp output of jobs that were in progress. The name is
    /// <c>{stem}.refiner.XXXXXXXX{suffix}</c> of the job's <c>relative_media_path</c>, in its library's
    /// effective work folder.
    /// </summary>
    public static int RemoveInterruptedRemuxTempFiles(
        IReadOnlyList<InterruptedJob> interrupted,
        IReadOnlyList<RefinerLibraryFolderRow> libraries,
        string weirHome,
        ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(interrupted);
        ArgumentNullException.ThrowIfNull(logger);
        var removed = 0;
        foreach (var job in interrupted)
        {
            var payload = JobPayload.ParseObject(job.PayloadJson);
            var relative = JobPayload.StringProperty(payload, "relative_media_path")?.Trim();
            if (string.IsNullOrEmpty(relative))
            {
                continue;
            }

            var scope = JobPayload.StringProperty(payload, "media_scope");
            var library = RefinerLibraryFolders.Resolve(libraries, JobPayload.LooseInteger(payload, "library_id"), scope);
            var workFolder = library is not null
                ? RefinerLibraryFolders.EffectiveWorkFolder(library, weirHome)
                : RefinerLibraryFolders.NormalizeMediaScope(scope) == "tv"
                    ? RefinerLibraryFolders.DefaultTvWorkFolder(weirHome)
                    : RefinerLibraryFolders.DefaultMovieWorkFolder(weirHome);
            var pattern = WeirTempFiles.RemuxTempNameFor(relative);
            removed += DeleteMatching(workFolder, pattern.IsMatch, logger, job.Id);
        }

        return removed;
    }

    /// <summary>#534: remove remux temp output left at the top of every library work folder and the default ones.</summary>
    public static int SweepWorkFolderTempFiles(IReadOnlyList<RefinerLibraryFolderRow> libraries, string weirHome, ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(libraries);
        var roots = WorkRoots(libraries, weirHome);
        return roots.Sum(root => DeleteMatching(root, WeirTempFiles.IsRemuxTempName, logger, jobId: null));
    }

    /// <summary>
    /// <c>cleanup_refiner_partial_output_files</c>: hidden <c>*.partial</c> files under every library output
    /// folder and <c>WEIR_HOME/refiner-output</c>, searched recursively.
    /// </summary>
    public static int CleanupPartialOutputFiles(IReadOnlyList<RefinerLibraryFolderRow> libraries, string weirHome)
    {
        ArgumentNullException.ThrowIfNull(libraries);
        var comparer = OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal;
        var roots = new HashSet<string>(comparer);
        foreach (var library in libraries)
        {
            var text = library.OutputFolder.Trim();
            if (text.Length > 0)
            {
                roots.Add(RefinerLibraryFolders.ExpandForFilesystem(text));
            }
        }

        roots.Add(RefinerLibraryFolders.ExpandForFilesystem(Path.Join(weirHome, "refiner-output")));

        var removed = 0;
        foreach (var root in roots)
        {
            if (!Directory.Exists(root))
            {
                continue;
            }

            IEnumerable<string> candidates;
            try
            {
                candidates = Directory.EnumerateFiles(root, "*", new EnumerationOptions
                {
                    RecurseSubdirectories = true,
                    IgnoreInaccessible = true,
                    AttributesToSkip = 0,
                    ReturnSpecialDirectories = false,
                }).ToList();
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                continue;
            }

            foreach (var path in candidates)
            {
                if (!WeirTempFiles.IsPartialOutputName(Path.GetFileName(path), ignoreCase: OperatingSystem.IsWindows()))
                {
                    continue;
                }

                try
                {
                    File.Delete(path);
                    removed++;
                }
                catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
                {
                    // Python: except OSError: continue
                }
            }
        }

        return removed;
    }

    private static HashSet<string> WorkRoots(IReadOnlyList<RefinerLibraryFolderRow> libraries, string weirHome)
    {
        var comparer = OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal;
        var roots = new HashSet<string>(comparer)
        {
            RefinerLibraryFolders.DefaultMovieWorkFolder(weirHome),
            RefinerLibraryFolders.DefaultTvWorkFolder(weirHome),
        };
        foreach (var library in libraries)
        {
            roots.Add(RefinerLibraryFolders.ExpandForFilesystem(RefinerLibraryFolders.EffectiveWorkFolder(library, weirHome)));
        }

        return roots;
    }

    private static int DeleteMatching(string folder, Func<string, bool> isWeirTempName, ILogger logger, long? jobId)
    {
        string root;
        try
        {
            root = RefinerLibraryFolders.ExpandForFilesystem(folder);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return 0;
        }

        if (!Directory.Exists(root))
        {
            return 0;
        }

        List<string> files;
        try
        {
            files = [.. Directory.EnumerateFiles(root, "*", new EnumerationOptions { RecurseSubdirectories = false, AttributesToSkip = 0 })];
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            logger.LogWarning("Weir startup could not read work folder {Folder} to remove interrupted temp files: {Error}", root, exception.Message);
            return 0;
        }

        var removed = 0;
        foreach (var path in files)
        {
            if (!isWeirTempName(Path.GetFileName(path)))
            {
                continue;
            }

            try
            {
                File.Delete(path);
                removed++;
                logger.LogInformation(
                    "Removed interrupted Refiner temp output {Path}{JobSuffix}",
                    path,
                    jobId is { } id ? string.Create(CultureInfo.InvariantCulture, $" job_id={id}") : string.Empty);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                logger.LogWarning("Weir startup could not remove interrupted temp file {Path}: {Error}", path, exception.Message);
            }
        }

        return removed;
    }
}
