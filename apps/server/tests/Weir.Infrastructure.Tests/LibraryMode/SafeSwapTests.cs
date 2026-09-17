using Microsoft.Extensions.Logging;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Tests.Media;

namespace Weir.Infrastructure.Tests.LibraryMode;

/// <summary>A swap over the in-memory filesystem: one library file, "OLD", replaced by a cleaned copy, "NEW".</summary>
internal sealed class SwapScenario
{
    public const string Library = "/lib";
    public const string Original = "/lib/Movie (2020)/Movie (2020).mkv";
    public const long JobId = 42;

    public static readonly string Temp = SafeSwapRules.TempPath(Original);
    public static readonly string Backup = SafeSwapRules.BackupPath(Original);

    public SwapScenario()
    {
        Files.Put(Original, "OLD");
        Journal = new FakeSwapJournal(Files);
        Swap = new SafeSwap(Files, Journal, Validator, SwapLogger);
        Sweep = new SwapRecoverySweep(Files, Journal, SweepLogger);
    }

    public FakeSwapFileSystem Files { get; } = new();

    public FakeSwapJournal Journal { get; }

    public FakeValidator Validator { get; } = new();

    public ListLogger<SafeSwap> SwapLogger { get; } = new();

    public ListLogger<SwapRecoverySweep> SweepLogger { get; } = new();

    public SafeSwap Swap { get; }

    public SwapRecoverySweep Sweep { get; }

    public List<string> WrittenTo { get; } = [];

    /// <summary>What the "ffmpeg" of the scenario does. Defaults to writing NEW.</summary>
    public Func<string, CancellationToken, Task>? Writer { get; set; }

    public Task<SwapResult> RunAsync(SwapOptions? options = null, CancellationToken cancellationToken = default) =>
        Swap.RunAsync(
            JobId,
            Original,
            (temp, token) =>
            {
                WrittenTo.Add(temp);
                if (Writer is not null)
                {
                    return Writer(temp, token);
                }

                Files.Write(temp, "NEW");
                return Task.CompletedTask;
            },
            options,
            cancellationToken);
}

public sealed class SafeSwapTests
{
    private const string Original = SwapScenario.Original;
    private static readonly string Temp = SwapScenario.Temp;
    private static readonly string Backup = SwapScenario.Backup;

    [Fact]
    public async Task A_clean_swap_puts_the_cleaned_copy_under_the_original_name_and_leaves_nothing_else()
    {
        var s = new SwapScenario();
        s.Files.SetPermissions(Original, "rw-r-----");
        var before = s.Files.Fingerprint(Original);

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.Equal(SafeSwapRules.CommittedMessage, result.Message);
        Assert.True(result.BackupRemoved);
        Assert.Empty(result.Warnings);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("NEW", s.Files.Read(Original));
        Assert.Equal("rw-r-----", s.Files.PermissionsOf(Original));
        Assert.NotEqual(before.ModifiedTimeNs, s.Files.Fingerprint(Original).ModifiedTimeNs);
        Assert.Equal(["/lib/Movie (2020)/Movie (2020).weir-tmp.mkv"], s.WrittenTo);
        Assert.Equal([Temp], s.Validator.Checked);
        Assert.Equal(
            [SwapJournalState.Writing, SwapJournalState.Committing, SwapJournalState.Committed, SwapJournalState.Finished],
            s.Journal.History.Select(entry => entry.State));
        Assert.All(s.Journal.History, entry => Assert.Equal((SwapScenario.JobId, Original), (entry.JobId, entry.OriginalPath)));
    }

    [Fact]
    public async Task The_steps_run_in_the_documented_order()
    {
        var s = new SwapScenario();
        await s.RunAsync();

        Assert.Equal(
            [
                $"FileExists({Backup})", $"FileExists({Temp})", $"FileExists({Temp})", $"FileExists({Backup})",
                $"FileExists({Original})", $"Fingerprint({Original})", $"LinkCount({Original})",
                $"AvailableFreeBytes({Path.GetDirectoryName(Original)})", $"ProbeWrite({Path.GetDirectoryName(Original)})",
                $"IsReadOnly({Original})", $"IsInUse({Original})",
                "Journal(Writing)",
                $"FileExists({Temp})", $"FileExists({Original})", $"Fingerprint({Original})",
                $"CopyPermissions({Original} -> {Temp})",
                "Journal(Committing)",
                $"Move({Original} -> {Backup})", $"Fingerprint({Backup})",
                $"Move({Temp} -> {Original})",
                "Journal(Committed)",
                $"Delete({Backup})",
                "Journal(Finished)",
            ],
            s.Files.Operations);
    }

    /// <summary>Every operation of a clean swap, for every fault mode.</summary>
    public static TheoryData<FaultMode, int, string> EveryStep()
    {
        var clean = new SwapScenario();
        clean.RunAsync().GetAwaiter().GetResult();
        var data = new TheoryData<FaultMode, int, string>();
        foreach (var mode in Enum.GetValues<FaultMode>())
        {
            for (var index = 0; index < clean.Files.Operations.Count; index++)
            {
                data.Add(mode, index, clean.Files.Operations[index]);
            }
        }

        return data;
    }

    [Theory]
    [MemberData(nameof(EveryStep))]
    public async Task A_failure_or_crash_at_any_step_leaves_exactly_one_intact_file(FaultMode mode, int index, string operation)
    {
        var s = new SwapScenario();
        s.Files.FaultAt = index;
        s.Files.Mode = mode;

        var result = await s.RunAsync();

        Assert.Equal(operation, s.Files.Operations[index]);
        // The commit is the rename of the cleaned copy onto the original name, and nothing else.
        var committed = s.Files.Effects.Contains($"Move({Temp} -> {Original})");
        var expected = committed ? "NEW" : "OLD";

        if (mode is FaultMode.Throw or FaultMode.ThrowAfterEffect)
        {
            // The same process carried on: the original name already holds intact content, without any sweep.
            Assert.True(s.Files.Has(Original), $"{mode} at {operation}: the original name is empty");
            Assert.Equal(expected, s.Files.Read(Original));
            if (mode == FaultMode.Throw)
            {
                Assert.Equal(committed, result.Committed);
            }

            if (!result.Committed)
            {
                Assert.False(s.Files.Has(Temp), $"{mode} at {operation}: the temp file was left behind");
            }
        }
        else
        {
            Assert.True(s.Files.Crashed);
        }

        // The next start: the sweep over the journal alone (no folder walk) puts everything right.
        s.Files.Restart();
        var report = await s.Sweep.RunAsync([SwapScenario.Library], walkFolders: false);

        Assert.Equal(0, report.Problems);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal(expected, s.Files.Read(Original));
        Assert.Empty(await s.Journal.ListUnfinishedAsync());

        // A folder walk afterwards finds nothing more to do.
        var walk = await s.Sweep.RunAsync([SwapScenario.Library], walkFolders: true);
        Assert.Equal(SwapRecoveryReport.Empty, walk);
    }

    [Fact]
    public async Task The_fault_matrix_covers_every_mutation_of_the_swap()
    {
        var data = EveryStep();
        Assert.Equal(Enum.GetValues<FaultMode>().Length * 23, data.Count);
        var operations = data.Select(row => (string)row[2]).Distinct().ToList();
        Assert.Contains($"Move({Original} -> {Backup})", operations);
        Assert.Contains($"Move({Temp} -> {Original})", operations);
        Assert.Contains($"Delete({Backup})", operations);
        Assert.Contains("Journal(Committed)", operations);
        await Task.CompletedTask;
    }

    [Fact]
    public async Task A_change_to_the_original_during_the_write_replaces_nothing()
    {
        var s = new SwapScenario();
        s.Writer = (temp, _) =>
        {
            s.Files.Write(temp, "NEW");
            s.Files.Write(Original, "MANAGER IMPORTED A NEWER COPY");
            return Task.CompletedTask;
        };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.SourceChanged, result.Outcome);
        Assert.Equal("The file changed while Weir was working; nothing was replaced", result.Message);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("MANAGER IMPORTED A NEWER COPY", s.Files.Read(Original));
        Assert.Equal(SwapJournalState.RolledBack, s.Journal.Latest(SwapScenario.JobId)!.State);
    }

    [Fact]
    public async Task A_change_to_the_original_during_validation_replaces_nothing()
    {
        var s = new SwapScenario();
        s.Validator.During = () => s.Files.Write(Original, "OLD, appended to");

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.SourceChanged, result.Outcome);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("OLD, appended to", s.Files.Read(Original));
    }

    [Fact]
    public async Task A_replaced_original_with_the_same_size_is_caught_by_its_identity()
    {
        var s = new SwapScenario();
        s.Writer = (temp, _) =>
        {
            s.Files.Write(temp, "NEW");
            s.Files.Put(Original, "OLD"); // a different file (new inode, new mtime) with the same size
            return Task.CompletedTask;
        };

        Assert.Equal(SwapOutcome.SourceChanged, (await s.RunAsync()).Outcome);
        Assert.Equal([Original], s.Files.Paths);
    }

    [Fact]
    public async Task A_deleted_original_is_not_replaced_by_the_cleaned_copy()
    {
        var s = new SwapScenario();
        s.Writer = (temp, _) =>
        {
            s.Files.Write(temp, "NEW");
            s.Files.Delete(Original);
            return Task.CompletedTask;
        };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.SourceChanged, result.Outcome);
        Assert.Empty(s.Files.Paths);
    }

    [Fact]
    public async Task A_write_to_the_original_as_it_is_moved_aside_is_caught_and_the_original_put_back()
    {
        var s = new SwapScenario();
        s.Files.OnStep = operation =>
        {
            if (operation == $"Fingerprint({Backup})")
            {
                s.Files.Write(Backup, "OLD plus bytes a writer added through its open handle");
            }
        };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.SourceChanged, result.Outcome);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("OLD plus bytes a writer added through its open handle", s.Files.Read(Original));
    }

    [Fact]
    public async Task A_newer_file_that_appears_under_the_original_name_mid_commit_is_never_overwritten()
    {
        var s = new SwapScenario();
        s.Files.OnStep = operation =>
        {
            if (operation == $"Move({Temp} -> {Original})")
            {
                s.Files.Put(Original, "MANAGER");
            }
        };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Failed, result.Outcome);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("MANAGER", s.Files.Read(Original));
    }

    [Fact]
    public async Task Output_that_fails_validation_is_discarded_and_the_original_kept()
    {
        var s = new SwapScenario();
        s.Validator.Answer = SwapValidation.Fail("the output is 40 minutes shorter than the source");

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.ValidationFailed, result.Outcome);
        Assert.Equal(
            "The cleaned copy did not pass Weir's output checks, so the original was kept: the output is 40 minutes shorter than the source",
            result.Message);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("OLD", s.Files.Read(Original));
    }

    [Fact]
    public async Task A_validator_that_throws_rolls_back()
    {
        var s = new SwapScenario();
        s.Validator.Throw = new InvalidOperationException("ffprobe crashed");

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Failed, result.Outcome);
        Assert.Contains("ffprobe crashed", result.Message, StringComparison.Ordinal);
        Assert.Equal([Original], s.Files.Paths);
    }

    [Fact]
    public async Task A_writer_that_fails_part_way_leaves_no_temp_file()
    {
        var s = new SwapScenario();
        s.Writer = (temp, _) =>
        {
            s.Files.Write(temp, "NE");
            throw new IOException("No space left on device");
        };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Failed, result.Outcome);
        Assert.Equal(
            "Weir could not finish replacing the file while writing the cleaned copy, so the original was kept. The system reported: No space left on device",
            result.Message);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("OLD", s.Files.Read(Original));
    }

    [Fact]
    public async Task A_writer_that_writes_nothing_fails_without_touching_the_original()
    {
        var s = new SwapScenario { Writer = (_, _) => Task.CompletedTask };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Failed, result.Outcome);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Empty(s.Validator.Checked);
    }

    [Fact]
    public async Task Cancellation_during_the_write_rolls_back_and_rethrows()
    {
        using var cancel = new CancellationTokenSource();
        var s = new SwapScenario();
        s.Writer = (temp, token) =>
        {
            s.Files.Write(temp, "NE");
            cancel.Cancel();
            token.ThrowIfCancellationRequested();
            return Task.CompletedTask;
        };

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => s.RunAsync(cancellationToken: cancel.Token));

        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("OLD", s.Files.Read(Original));
        Assert.Equal(SwapJournalState.RolledBack, s.Journal.Latest(SwapScenario.JobId)!.State);
    }

    [Fact]
    public async Task A_hardlinked_file_is_skipped_before_any_work()
    {
        var s = new SwapScenario();
        s.Files.Put(Original, "OLD", links: 2);

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Hardlinked, result.Outcome);
        Assert.Equal(SafeSwapRules.HardlinkedMessage, result.Message);
        Assert.Empty(s.WrittenTo);
        Assert.Empty(s.Journal.History);
        Assert.Equal([Original], s.Files.Paths);
    }

    [Fact]
    public async Task A_hardlinked_file_is_replaced_when_the_library_allows_it()
    {
        var s = new SwapScenario();
        s.Files.Put(Original, "OLD", links: 2);

        var result = await s.RunAsync(new SwapOptions(AllowHardlinked: true));

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.Equal("NEW", s.Files.Read(Original));
    }

    [Fact]
    public async Task An_unknown_link_count_is_noted_but_does_not_block()
    {
        var s = new SwapScenario();
        s.Files.LinkCountUnknown = true;

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.Contains("Weir could not check whether this file is hardlinked on this platform.", result.Warnings);
    }

    [Fact]
    public async Task Insufficient_space_is_refused_and_exactly_enough_is_allowed()
    {
        var s = new SwapScenario();
        s.Files.FreeBytes = 3 + SafeSwapRules.FreeSpaceMarginBytes - 1;

        var refused = await s.RunAsync();

        Assert.Equal(SwapOutcome.InsufficientSpace, refused.Outcome);
        Assert.Equal(
            "There is not enough free space next to this file for Weir to write the cleaned copy: it needs 1.0 GB (the file's size plus 1 GB to spare) and 1.0 GB is free. Nothing was changed.",
            refused.Message);
        Assert.Empty(s.WrittenTo);

        s.Files.FreeBytes = 3 + SafeSwapRules.FreeSpaceMarginBytes;
        Assert.Equal(SwapOutcome.Committed, (await s.RunAsync()).Outcome);
    }

    [Fact]
    public async Task A_folder_Weir_cannot_write_to_is_refused()
    {
        var s = new SwapScenario();
        s.Files.WriteProblem = "Access to the path is denied.";

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.NotWritable, result.Outcome);
        Assert.Equal("Weir cannot write to this file's folder, so it did not start. The system reported: Access to the path is denied.", result.Message);
        Assert.Empty(s.WrittenTo);
    }

    [Fact]
    public async Task A_read_only_file_is_refused()
    {
        var s = new SwapScenario();
        s.Files.SetReadOnly(Original);

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.NotWritable, result.Outcome);
        Assert.Equal(SafeSwapRules.ReadOnlyMessage, result.Message);
    }

    [Fact]
    public async Task A_missing_file_is_reported_as_missing()
    {
        var s = new SwapScenario();
        s.Files.Delete(Original);

        Assert.Equal(SwapOutcome.SourceMissing, (await s.RunAsync()).Outcome);
    }

    [Fact]
    public async Task A_file_in_use_before_the_work_is_an_in_use_result_not_a_failure()
    {
        var s = new SwapScenario();
        s.Files.SetInUse(Original);

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.InUse, result.Outcome);
        Assert.Equal(SafeSwapRules.InUseMessage, result.Message);
        Assert.Empty(s.WrittenTo);
    }

    [Fact]
    public async Task A_file_locked_at_the_commit_is_an_in_use_result_with_the_original_untouched()
    {
        var s = new SwapScenario();
        s.Writer = (temp, _) =>
        {
            s.Files.Write(temp, "NEW");
            s.Files.LockedForRename.Add(Original); // playback started while Weir was writing
            return Task.CompletedTask;
        };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.InUse, result.Outcome);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("OLD", s.Files.Read(Original));
        Assert.Equal(SwapJournalState.RolledBack, s.Journal.Latest(SwapScenario.JobId)!.State);
        Assert.Contains(s.SwapLogger.Entries, entry => entry.Level == LogLevel.Information && entry.Message.Contains("in use", StringComparison.Ordinal));
    }

    [Fact]
    public async Task A_backup_that_cannot_be_deleted_is_left_for_the_sweep_and_the_swap_still_commits()
    {
        var s = new SwapScenario();
        s.Files.LockedForRename.Add(Backup);

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.False(result.BackupRemoved);
        Assert.Single(result.Warnings);
        Assert.Equal("NEW", s.Files.Read(Original));
        Assert.True(s.Files.Has(Backup));
        Assert.Equal(SwapJournalState.Committed, s.Journal.Latest(SwapScenario.JobId)!.State);
        Assert.Contains(s.SwapLogger.Entries, entry => entry.Level == LogLevel.Warning && entry.Message.Contains("startup sweep", StringComparison.Ordinal));

        s.Files.LockedForRename.Clear();
        var report = await s.Sweep.RunAsync([], walkFolders: false);

        Assert.Equal(1, report.BackupsDeleted);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("NEW", s.Files.Read(Original));
    }

    [Fact]
    public async Task A_journal_that_cannot_record_the_commit_does_not_undo_it()
    {
        var s = new SwapScenario();
        s.Files.OnStep = operation =>
        {
            if (operation == "Journal(Committed)")
            {
                s.Files.FaultAt = s.Files.Operations.Count - 1;
            }
        };

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.Contains(result.Warnings, warning => warning.StartsWith("Weir replaced the file but could not record it on the job", StringComparison.Ordinal));
        Assert.Equal([Original], s.Files.Paths);
    }

    [Fact]
    public async Task Leftovers_of_an_earlier_swap_of_the_same_file_are_put_right_first()
    {
        var s = new SwapScenario();
        s.Files.Put(Backup, "an old backup");
        s.Files.Put(Temp, "an old temp");

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.Equal([Original], s.Files.Paths);
        Assert.Equal("NEW", s.Files.Read(Original));
    }

    [Fact]
    public async Task Leftovers_that_cannot_be_removed_stop_the_swap_before_any_work()
    {
        var s = new SwapScenario();
        s.Files.Put(Backup, "an old backup");
        s.Files.LockedForRename.Add(Backup);

        var result = await s.RunAsync();

        Assert.Equal(SwapOutcome.Failed, result.Outcome);
        Assert.Empty(s.WrittenTo);
        Assert.Equal("OLD", s.Files.Read(Original));
    }

    [Fact]
    public void Preflight_changes_nothing()
    {
        var s = new SwapScenario();
        var preflight = s.Swap.Preflight(Original);

        Assert.True(preflight.Ready);
        Assert.Equal(Temp, preflight.TempPath);
        Assert.Equal(Backup, preflight.BackupPath);
        Assert.DoesNotContain(
            s.Files.Effects,
            effect => effect.StartsWith("Move", StringComparison.Ordinal) || effect.StartsWith("Delete", StringComparison.Ordinal) ||
                      effect.StartsWith("CopyPermissions", StringComparison.Ordinal) || effect.StartsWith("Journal", StringComparison.Ordinal));
        Assert.Empty(s.Journal.History);
    }

    [Theory]
    [InlineData(7ul, 100ul, 3L, 5L, 7ul, 100ul, 3L, 5L, true)]
    [InlineData(7ul, 100ul, 3L, 5L, 7ul, 101ul, 3L, 5L, false)]
    [InlineData(7ul, 100ul, 3L, 5L, 7ul, 100ul, 4L, 5L, false)]
    [InlineData(7ul, 100ul, 3L, 5L, 7ul, 100ul, 3L, 6L, false)]
    [InlineData(0ul, 0ul, 3L, 5L, 7ul, 100ul, 3L, 5L, true)]
    [InlineData(7ul, 100ul, 3L, 5L, 0ul, 0ul, 3L, 5L, true)]
    public void Fingerprints_compare_identity_only_when_both_sides_read_it(
        ulong device1, ulong inode1, long size1, long mtime1, ulong device2, ulong inode2, long size2, long mtime2, bool same)
    {
        Assert.Equal(same, SafeSwap.SameFile(new SourceFingerprint(device1, inode1, size1, mtime1), new SourceFingerprint(device2, inode2, size2, mtime2)));
    }
}
