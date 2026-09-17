using Microsoft.Extensions.Logging;
using Weir.Core.LibraryMode;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>What recovery did.</summary>
public sealed record SwapRecoveryReport(int TempFilesDeleted, int BackupsDeleted, int BackupsRestored, int Problems)
{
    public static SwapRecoveryReport Empty { get; } = new(0, 0, 0, 0);

    public int FilesChanged => TempFilesDeleted + BackupsDeleted + BackupsRestored;

    public static SwapRecoveryReport operator +(SwapRecoveryReport left, SwapRecoveryReport right)
    {
        ArgumentNullException.ThrowIfNull(left);
        ArgumentNullException.ThrowIfNull(right);
        return new(
            left.TempFilesDeleted + right.TempFilesDeleted,
            left.BackupsDeleted + right.BackupsDeleted,
            left.BackupsRestored + right.BackupsRestored,
            left.Problems + right.Problems);
    }

    public static SwapRecoveryReport Add(SwapRecoveryReport left, SwapRecoveryReport right) => left + right;
}

/// <summary>
/// The startup sweep for interrupted library swaps (#506), after Muxarr's <c>CleanupMuxbakFiles</c> and <c>RestoreFromBackup</c>.
/// Run it before any worker starts.
/// </summary>
/// <remarks>
/// <para>For each original it looks at the files only, so it is correct whatever step a crash interrupted:</para>
/// <list type="bullet">
/// <item><c>&lt;name&gt;.weir-bak&lt;ext&gt;</c> and the original present → the commit happened (or a newer file arrived): delete the backup.</item>
/// <item><c>&lt;name&gt;.weir-bak&lt;ext&gt;</c> and the original missing → the commit did not happen: rename the backup back, with a warning.</item>
/// <item><c>&lt;name&gt;.weir-tmp&lt;ext&gt;</c> → delete it (a cleaned copy never put in place; the job runs again).</item>
/// </list>
/// <para>
/// The paths recorded on unfinished job rows (<see cref="ISwapJournal"/>) are handled first; walking the library folders is only a
/// fallback, for a journal that could not be written or a job row already pruned.
/// </para>
/// </remarks>
public sealed class SwapRecoverySweep
{
    private readonly ISwapFileSystem _files;
    private readonly ISwapJournal _journal;
    private readonly ILogger _logger;

    public SwapRecoverySweep(ISwapFileSystem files, ISwapJournal journal, ILogger<SwapRecoverySweep> logger)
    {
        _files = files;
        _journal = journal;
        _logger = logger;
    }

    /// <param name="libraryFolders">Library folders to walk when <paramref name="walkFolders"/> is set.</param>
    /// <param name="walkFolders">Also look for leftovers the journal does not know about.</param>
    /// <param name="cancellationToken">Stops between files.</param>
    public async Task<SwapRecoveryReport> RunAsync(
        IEnumerable<string> libraryFolders,
        bool walkFolders,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(libraryFolders);
        var report = SwapRecoveryReport.Empty;
        var handled = new HashSet<string>(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);

        IReadOnlyList<SwapJournalEntry> unfinished;
        try
        {
            unfinished = await _journal.ListUnfinishedAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            _logger.LogWarning(exception, "Library swap sweep could not read the swaps recorded on job rows; only a folder walk can find leftovers");
            unfinished = [];
            report += new SwapRecoveryReport(0, 0, 0, 1);
        }

        foreach (var entry in unfinished)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var fileReport = RecoverFile(_files, entry.OriginalPath, _logger);
            report += fileReport;
            handled.Add(entry.OriginalPath);
            if (fileReport.Problems > 0)
            {
                continue;
            }

            try
            {
                await _journal.RecordAsync(entry with { State = SwapJournalState.Recovered }, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                _logger.LogWarning(exception, "Library swap sweep recovered a file but could not record it job_id={JobId} path={Path}", entry.JobId, entry.OriginalPath);
            }
        }

        if (!walkFolders)
        {
            return Log(report);
        }

        foreach (var folder in libraryFolders.Where(folder => !string.IsNullOrWhiteSpace(folder)))
        {
            List<string> leftovers;
            try
            {
                leftovers = _files.EnumerateLeftovers(folder).ToList();
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException)
            {
                _logger.LogWarning(exception, "Library swap sweep could not walk folder={Folder}", folder);
                report += new SwapRecoveryReport(0, 0, 0, 1);
                continue;
            }

            foreach (var leftover in leftovers)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (SafeSwapRules.TryParseLeftover(leftover, out _, out var original) && handled.Add(original))
                {
                    report += RecoverFile(_files, original, _logger);
                }
            }
        }

        return Log(report);
    }

    /// <summary>Put one original's leftovers right (see the class remarks). Never throws; failures are counted and logged.</summary>
    /// <param name="files">The filesystem.</param>
    /// <param name="originalPath">The library file whose leftovers are checked.</param>
    /// <param name="logger">Where each action is logged.</param>
    /// <param name="restoreQuietly">A rollback restoring its own backup: expected, so not a warning.</param>
    public static SwapRecoveryReport RecoverFile(ISwapFileSystem files, string originalPath, ILogger logger, bool restoreQuietly = false)
    {
        ArgumentNullException.ThrowIfNull(files);
        ArgumentNullException.ThrowIfNull(logger);
        var backup = SafeSwapRules.BackupPath(originalPath);
        var temp = SafeSwapRules.TempPath(originalPath);
        int tempsDeleted = 0, backupsDeleted = 0, backupsRestored = 0, problems = 0;

        try
        {
            if (files.FileExists(backup))
            {
                if (files.FileExists(originalPath))
                {
                    files.Delete(backup);
                    backupsDeleted++;
                    logger.LogInformation("Library swap backup removed; the file under the original name is kept backup={Backup}", backup);
                }
                else
                {
                    files.Move(backup, originalPath);
                    backupsRestored++;
                    if (restoreQuietly)
                    {
                        logger.LogInformation("Library swap put the original back path={Path}", originalPath);
                    }
                    else
                    {
                        logger.LogWarning(
                            "Weir restored a library file from its backup: a swap was interrupted before the cleaned copy was in place path={Path}",
                            originalPath);
                    }
                }
            }
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            problems++;
            logger.LogWarning(exception, "Library swap recovery could not deal with the backup backup={Backup}", backup);
        }

        try
        {
            if (files.FileExists(temp))
            {
                files.Delete(temp);
                tempsDeleted++;
            }
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            problems++;
            logger.LogWarning(exception, "Library swap recovery could not delete the temp file temp={Temp}", temp);
        }

        return new SwapRecoveryReport(tempsDeleted, backupsDeleted, backupsRestored, problems);
    }

    private SwapRecoveryReport Log(SwapRecoveryReport report)
    {
        if (report.FilesChanged > 0 || report.Problems > 0)
        {
            _logger.LogWarning(
                "Library swap sweep finished temp_files_deleted={TempFilesDeleted} backups_deleted={BackupsDeleted} backups_restored={BackupsRestored} problems={Problems}",
                report.TempFilesDeleted,
                report.BackupsDeleted,
                report.BackupsRestored,
                report.Problems);
        }

        return report;
    }
}
