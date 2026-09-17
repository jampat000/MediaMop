using Microsoft.Extensions.Logging;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>Whether a written cleaned copy may replace the original (#500's full output check plugs in here).</summary>
public interface ISwapOutputValidator
{
    Task<SwapValidation> ValidateAsync(string originalPath, string outputPath, CancellationToken cancellationToken);
}

/// <summary>An output check's answer.</summary>
public sealed record SwapValidation(bool Passed, string? Problem)
{
    public static SwapValidation Pass { get; } = new(true, null);

    public static SwapValidation Fail(string problem) => new(false, problem);
}

/// <summary>Writes the cleaned copy of the original to <paramref name="tempPath"/> (ffmpeg, for the remux pass).</summary>
public delegate Task SwapOutputWriter(string tempPath, CancellationToken cancellationToken);

/// <summary>Per-library choices that change preflight.</summary>
/// <param name="AllowHardlinked"><c>clean_hardlinked_files</c> (#508): replace a file that has other hard links anyway.</param>
public sealed record SwapOptions(bool AllowHardlinked = false)
{
    public static SwapOptions Default { get; } = new();
}

/// <summary>What preflight found. <see cref="Refusal"/> is null when the swap may go ahead.</summary>
public sealed record SwapPreflight(
    string OriginalPath,
    SwapOutcome? Refusal,
    string? Message,
    SourceFingerprint Fingerprint,
    IReadOnlyList<string> Notes)
{
    public bool Ready => Refusal is null;

    public string TempPath => SafeSwapRules.TempPath(OriginalPath);

    public string BackupPath => SafeSwapRules.BackupPath(OriginalPath);
}

/// <summary>
/// How a swap ended, in words for the operator, plus anything worth a warning. After a commit, <c>BackupRemoved</c> is false
/// when the backup could not be deleted (the startup sweep retries it).
/// </summary>
public sealed record SwapResult(SwapOutcome Outcome, string Message, bool BackupRemoved, IReadOnlyList<string> Warnings)
{
    public bool Committed => Outcome == SwapOutcome.Committed;
}

/// <summary>
/// The crash-safe in-place swap for library mode (#506): a file in a library is replaced by its cleaned copy so that a crash,
/// power cut, locked file or concurrent change can never lose it or overwrite a newer one.
/// </summary>
/// <remarks>
/// <para>Steps, each of which may fail (the tests inject a failure, and a crash, at every one):</para>
/// <list type="number">
/// <item>Put right any leftovers of an earlier swap of this file (<see cref="SwapRecoverySweep.RecoverFile"/>).</item>
/// <item>Preflight: present, not hardlinked (#508), free space for a copy plus 1 GiB, folder writable, not read-only, not in use; fingerprint.</item>
/// <item>Journal <c>writing</c>; write <c>&lt;name&gt;.weir-tmp&lt;ext&gt;</c> beside the original; validate it.</item>
/// <item>Re-fingerprint the original: changed → discard the copy, "The file changed while Weir was working; nothing was replaced".</item>
/// <item>Copy the original's permissions to the copy (best effort; never the mtime).</item>
/// <item>Journal <c>committing</c>; rename original → <c>&lt;name&gt;.weir-bak&lt;ext&gt;</c>; check the backup is still the fingerprinted file.</item>
/// <item>Rename copy → original name. <b>This rename is the commit.</b></item>
/// <item>Journal <c>committed</c> (<c>swap_committed</c>); delete the backup (a failure is logged, the sweep retries); journal <c>finished</c>.</item>
/// </list>
/// <para>
/// Any failure before the commit rolls back by looking at the files, not at how far the code got: if the original name is
/// empty and the backup exists the backup is renamed back, and the temp file is deleted. A crash skips the rollback, and
/// <see cref="SwapRecoverySweep"/> applies the same rules at the next start. Either way exactly one intact file is left under the
/// original name: the original content before the commit rename, the cleaned content after it.
/// </para>
/// <para>
/// A file held by another program (a Windows sharing violation, <c>EBUSY</c>) is not a failure: the result is
/// <see cref="SwapOutcome.InUse"/> and the caller requeues it with <see cref="SafeSwapRules.InUseRetryDelay"/>.
/// </para>
/// </remarks>
public sealed class SafeSwap
{
    private readonly ISwapFileSystem _files;
    private readonly ISwapJournal _journal;
    private readonly ISwapOutputValidator _validator;
    private readonly ILogger _logger;
    private readonly IOutputOwnership? _ownership;

    public SafeSwap(ISwapFileSystem files, ISwapJournal journal, ISwapOutputValidator validator, ILogger<SafeSwap> logger, IOutputOwnership? ownership = null)
    {
        _files = files;
        _journal = journal;
        _validator = validator;
        _logger = logger;
        _ownership = ownership;
    }

    /// <summary>The checks made before any work, without changing anything. A scan can show the refusal reasons.</summary>
    public SwapPreflight Preflight(string originalPath, SwapOptions? options = null)
    {
        ArgumentException.ThrowIfNullOrEmpty(originalPath);
        options ??= SwapOptions.Default;
        var notes = new List<string>();
        SwapPreflight Refuse(SwapOutcome outcome, string message, SourceFingerprint fingerprint = default) =>
            new(originalPath, outcome, message, fingerprint, notes);

        try
        {
            if (!_files.FileExists(originalPath))
            {
                return Refuse(SwapOutcome.SourceMissing, SafeSwapRules.SourceMissingMessage);
            }

            var fingerprint = _files.Fingerprint(originalPath);
            var links = _files.LinkCount(originalPath);
            if (links is null)
            {
                notes.Add("Weir could not check whether this file is hardlinked on this platform.");
            }
            else if (links > 1 && !options.AllowHardlinked)
            {
                return Refuse(SwapOutcome.Hardlinked, SafeSwapRules.HardlinkedMessage, fingerprint);
            }

            var directory = DirectoryOf(originalPath);
            var required = SafeSwapRules.RequiredFreeBytes(fingerprint.SizeBytes);
            var available = _files.AvailableFreeBytes(directory);
            if (available is null)
            {
                notes.Add("Weir could not read the free space on this file's volume.");
            }
            else if (available < required)
            {
                return Refuse(SwapOutcome.InsufficientSpace, SafeSwapRules.InsufficientSpaceMessage(required, available.Value), fingerprint);
            }

            try
            {
                _files.ProbeWrite(directory);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                return Refuse(SwapOutcome.NotWritable, SafeSwapRules.NotWritableMessage(exception.Message), fingerprint);
            }

            if (_files.IsReadOnly(originalPath))
            {
                return Refuse(SwapOutcome.NotWritable, SafeSwapRules.ReadOnlyMessage, fingerprint);
            }

            if (_files.IsInUse(originalPath))
            {
                return Refuse(SwapOutcome.InUse, SafeSwapRules.InUseMessage, fingerprint);
            }

            return new SwapPreflight(originalPath, null, null, fingerprint, notes);
        }
        catch (FileNotFoundException)
        {
            return Refuse(SwapOutcome.SourceMissing, SafeSwapRules.SourceMissingMessage);
        }
        catch (FileInUseException)
        {
            return Refuse(SwapOutcome.InUse, SafeSwapRules.InUseMessage);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return Refuse(SwapOutcome.Failed, SafeSwapRules.FailedMessage("checking the file before starting", exception.Message));
        }
    }

    /// <summary>
    /// Preflight, write the cleaned copy with <paramref name="writeOutput"/>, validate it and swap it in, recording progress on
    /// job <paramref name="jobId"/>. Never throws for a filesystem or journal failure; cancellation before the commit rolls back
    /// and rethrows, and is not observed once the commit has started.
    /// </summary>
    public async Task<SwapResult> RunAsync(
        long jobId,
        string originalPath,
        SwapOutputWriter writeOutput,
        SwapOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(originalPath);
        ArgumentNullException.ThrowIfNull(writeOutput);
        var temp = SafeSwapRules.TempPath(originalPath);
        var backup = SafeSwapRules.BackupPath(originalPath);
        var warnings = new List<string>();

        // An earlier swap of this file that stopped half-way: finish putting it right first, so a stale backup can never be
        // mistaken for this swap's (and restored over a newer file).
        SwapRecoverySweep.RecoverFile(_files, originalPath, _logger);
        if (Exists(temp) is not false || Exists(backup) is not false)
        {
            return new SwapResult(
                SwapOutcome.Failed,
                SafeSwapRules.FailedMessage("clearing up an earlier interrupted swap", "its leftover files could not be removed"),
                false,
                warnings);
        }

        var preflight = Preflight(originalPath, options);
        if (!preflight.Ready)
        {
            return new SwapResult(preflight.Refusal!.Value, preflight.Message!, false, warnings);
        }

        warnings.AddRange(preflight.Notes);
        var stage = "recording that the swap started";
        try
        {
            await _journal.RecordAsync(new SwapJournalEntry(jobId, originalPath, SwapJournalState.Writing), cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            _logger.LogWarning(exception, "Library swap not started: the journal could not be written job_id={JobId} path={Path}", jobId, originalPath);
            return new SwapResult(SwapOutcome.Failed, SafeSwapRules.FailedMessage(stage, exception.Message), false, warnings);
        }

        async Task<SwapResult> Abandon(SwapOutcome outcome, string message)
        {
            await RollbackAsync(jobId, originalPath).ConfigureAwait(false);
            return new SwapResult(outcome, message, false, warnings);
        }

        try
        {
            stage = "writing the cleaned copy";
            await writeOutput(temp, cancellationToken).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            if (!_files.FileExists(temp))
            {
                return await Abandon(SwapOutcome.Failed, SafeSwapRules.FailedMessage(stage, "no cleaned copy was written"));
            }

            stage = "checking the cleaned copy";
            var validation = await _validator.ValidateAsync(originalPath, temp, cancellationToken).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            if (!validation.Passed)
            {
                return await Abandon(SwapOutcome.ValidationFailed, SafeSwapRules.ValidationFailedMessage(validation.Problem));
            }

            stage = "checking the original again";
            if (!_files.FileExists(originalPath) || !SameFile(_files.Fingerprint(originalPath), preflight.Fingerprint))
            {
                _logger.LogWarning("Library swap abandoned: the original changed while Weir worked job_id={JobId} path={Path}", jobId, originalPath);
                return await Abandon(SwapOutcome.SourceChanged, SafeSwapRules.SourceChangedMessage);
            }

            // From here the swap takes milliseconds and is not cancelled part-way.
            stage = "copying the file's permissions";
            try
            {
                _files.CopyPermissions(originalPath, temp);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or PlatformNotSupportedException or InvalidOperationException)
            {
                _logger.LogWarning(exception, "Library swap could not copy the file's permissions job_id={JobId} path={Path}", jobId, originalPath);
                warnings.Add($"Weir could not give the cleaned file the original's permissions: {exception.Message}");
            }

            stage = "recording that the swap is committing";
            await _journal.RecordAsync(new SwapJournalEntry(jobId, originalPath, SwapJournalState.Committing), CancellationToken.None).ConfigureAwait(false);

            stage = "moving the original aside";
            _files.Move(originalPath, backup);

            stage = "checking the original again";
            if (!SameFile(_files.Fingerprint(backup), preflight.Fingerprint))
            {
                _logger.LogWarning("Library swap abandoned: the original changed as Weir moved it aside job_id={JobId} path={Path}", jobId, originalPath);
                return await Abandon(SwapOutcome.SourceChanged, SafeSwapRules.SourceChangedMessage);
            }

            stage = "putting the cleaned copy in place";
            _files.Move(temp, originalPath);
            // #555: the swapped-in file is a fresh name (the rename above), so it needs the output-ownership
            // policy applied like any other file Weir just published; never fails the swap.
            _ownership?.ApplyToFile(originalPath);
        }
        catch (OperationCanceledException)
        {
            await RollbackAsync(jobId, originalPath).ConfigureAwait(false);
            throw;
        }
        catch (FileInUseException exception)
        {
            _logger.LogInformation("Library swap postponed: the file is in use job_id={JobId} path={Path} stage={Stage} detail={Detail}", jobId, originalPath, stage, exception.Message);
            return await Abandon(SwapOutcome.InUse, SafeSwapRules.InUseMessage);
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Library swap rolled back job_id={JobId} path={Path} stage={Stage}", jobId, originalPath, stage);
            return await Abandon(SwapOutcome.Failed, SafeSwapRules.FailedMessage(stage, exception.Message));
        }

        // Committed: the cleaned copy has the original's name. Nothing below may undo that.
        _logger.LogInformation("Library swap committed job_id={JobId} path={Path}", jobId, originalPath);
        try
        {
            await _journal.RecordAsync(new SwapJournalEntry(jobId, originalPath, SwapJournalState.Committed), CancellationToken.None).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Library swap committed but not recorded job_id={JobId} path={Path}", jobId, originalPath);
            warnings.Add($"Weir replaced the file but could not record it on the job: {exception.Message}");
        }

        var backupRemoved = false;
        try
        {
            _files.Delete(backup);
            backupRemoved = true;
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Library swap left its backup for the startup sweep job_id={JobId} backup={Backup}", jobId, backup);
            warnings.Add($"Weir replaced the file but could not delete the backup copy ({backup}); it will try again when it next starts.");
        }

        if (backupRemoved)
        {
            try
            {
                await _journal.RecordAsync(new SwapJournalEntry(jobId, originalPath, SwapJournalState.Finished), CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception exception)
            {
                _logger.LogWarning(exception, "Library swap finished but not recorded job_id={JobId} path={Path}", jobId, originalPath);
            }
        }

        return new SwapResult(SwapOutcome.Committed, SafeSwapRules.CommittedMessage, backupRemoved, warnings);
    }

    /// <summary>Whether two fingerprints describe the same unchanged file. Device and inode are compared only when both were read.</summary>
    internal static bool SameFile(SourceFingerprint current, SourceFingerprint recorded)
    {
        if (current.SizeBytes != recorded.SizeBytes || current.ModifiedTimeNs != recorded.ModifiedTimeNs)
        {
            return false;
        }

        var identityKnown = (current.Device, current.Inode) != (0, 0) && (recorded.Device, recorded.Inode) != (0, 0);
        return !identityKnown || (current.Device == recorded.Device && current.Inode == recorded.Inode);
    }

    private static string DirectoryOf(string path)
    {
        var directory = Path.GetDirectoryName(path);
        return string.IsNullOrEmpty(directory) ? "." : directory;
    }

    /// <summary>Undo a swap that did not commit, judging from the files alone. Failures are logged; the sweep finishes the job.</summary>
    private async Task RollbackAsync(long jobId, string originalPath)
    {
        var report = SwapRecoverySweep.RecoverFile(_files, originalPath, _logger, restoreQuietly: true);
        if (report.Problems > 0)
        {
            _logger.LogWarning("Library swap rollback left files for the startup sweep job_id={JobId} path={Path}", jobId, originalPath);
            return;
        }

        try
        {
            await _journal.RecordAsync(new SwapJournalEntry(jobId, originalPath, SwapJournalState.RolledBack), CancellationToken.None).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "Library swap rolled back but not recorded job_id={JobId} path={Path}", jobId, originalPath);
        }
    }

    private bool? Exists(string path)
    {
        try
        {
            return _files.FileExists(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }
}
