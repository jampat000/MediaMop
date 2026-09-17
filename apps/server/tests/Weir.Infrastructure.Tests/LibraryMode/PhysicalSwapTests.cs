using System.Security.AccessControl;
using System.Security.Principal;
using Weir.Core.Json;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.LibraryMode;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Tests.Jobs;
using Weir.Infrastructure.Tests.Media;
using Weir.Infrastructure.Tests.Refiner.RemuxPass;

namespace Weir.Infrastructure.Tests.LibraryMode;

/// <summary>The swap and the sweep on real files in a temporary folder, journaled on a real job row.</summary>
public sealed class PhysicalSwapTests : IDisposable
{
    private static readonly DateTime OldTime = new(2001, 1, 1, 0, 0, 0, DateTimeKind.Utc);

    private readonly JobsTestDatabase _db = new();
    private readonly string _library;
    private readonly string _original;
    private readonly long _jobId;
    private readonly RefinerJobSwapJournal _journal;
    private readonly FakeValidator _validator = new();
    private readonly SafeSwap _swap;

    public PhysicalSwapTests()
    {
        _library = _db.Join("library");
        Directory.CreateDirectory(Path.Join(_library, "Movie (2020)"));
        _original = Path.Join(_library, "Movie (2020)", "Movie (2020).mkv");
        File.WriteAllText(_original, "original content");
        File.SetLastWriteTimeUtc(_original, OldTime);
        _db.Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status) VALUES ('library:1', 'refiner.library.clean.v1', $payload, 'leased')",
            ("$payload", "{\"library_id\":1,\"relative_media_path\":\"Movie (2020)/Movie (2020).mkv\"}"));
        _jobId = (long)_db.Scalar("SELECT id FROM refiner_jobs WHERE dedupe_key = 'library:1'")!;
        _journal = new RefinerJobSwapJournal(_db.Database);
        _swap = new SafeSwap(PhysicalSwapFileSystem.Instance, _journal, _validator, new ListLogger<SafeSwap>());
    }

    private string Temp => SafeSwapRules.TempPath(_original);

    private string Backup => SafeSwapRules.BackupPath(_original);

    public void Dispose()
    {
        if (File.Exists(_original))
        {
            File.SetAttributes(_original, FileAttributes.Normal);
        }

        _db.Dispose();
    }

    private Task<SwapResult> RunAsync(Action<string>? duringWrite = null) =>
        _swap.RunAsync(
            _jobId,
            _original,
            async (temp, token) =>
            {
                await File.WriteAllTextAsync(temp, "cleaned content", token);
                duringWrite?.Invoke(temp);
            });

    private string[] FilesInLibrary() =>
        Directory.GetFiles(_library, "*", SearchOption.AllDirectories).Select(path => Path.GetRelativePath(_library, path)).Order(StringComparer.Ordinal).ToArray();

    private PyDict Payload() => (PyDict)PyJsonParser.Parse((string)_db.Scalar("SELECT payload_json FROM refiner_jobs WHERE id = $id", ("$id", _jobId))!);

    private (string State, string OriginalPath, string TempPath, string BackupPath, bool Committed) SwapRow()
    {
        var row = _db.QueryRow("SELECT state, original_path, temp_path, backup_path, committed FROM library_swaps WHERE job_id = $id", ("$id", _jobId))
            ?? throw new InvalidOperationException("No library_swaps row was recorded for this job.");
        return ((string)row[0]!, (string)row[1]!, (string)row[2]!, (string)row[3]!, Convert.ToInt64(row[4]) != 0);
    }

    [Fact]
    public async Task A_real_file_is_replaced_in_place_with_a_new_mtime_and_the_job_row_records_it()
    {
        var result = await RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.True(result.BackupRemoved);
        Assert.Equal([Path.Join("Movie (2020)", "Movie (2020).mkv")], FilesInLibrary());
        Assert.Equal("cleaned content", await File.ReadAllTextAsync(_original));
        Assert.True(File.GetLastWriteTimeUtc(_original) > OldTime.AddYears(10), "the manager's rescan needs the mtime to move");

        // The job's own payload is never touched by the swap journal (#557 moved it to library_swaps).
        Assert.Equal(["library_id", "relative_media_path"], Payload().Keys);
        var swap = SwapRow();
        Assert.Equal("finished", swap.State);
        Assert.Equal(_original, swap.OriginalPath);
        Assert.Equal(Temp, swap.TempPath);
        Assert.Equal(Backup, swap.BackupPath);
        Assert.True(swap.Committed);
        Assert.Empty(await _journal.ListUnfinishedAsync());
    }

    [WindowsFact("Share modes that block a rename are a Windows behaviour.")]
    public async Task A_file_held_open_by_another_handle_is_in_use_before_any_work()
    {
        using (new FileStream(_original, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            Assert.True(PhysicalSwapFileSystem.Instance.IsInUse(_original));
            var result = await RunAsync();

            Assert.Equal(SwapOutcome.InUse, result.Outcome);
            Assert.Equal(SafeSwapRules.InUseMessage, result.Message);
        }

        Assert.Equal([Path.Join("Movie (2020)", "Movie (2020).mkv")], FilesInLibrary());
        Assert.Equal("original content", await File.ReadAllTextAsync(_original));
        Assert.False(PhysicalSwapFileSystem.Instance.IsInUse(_original));
    }

    [WindowsFact("Share modes that block a rename are a Windows behaviour.")]
    public async Task A_file_opened_by_a_player_during_the_write_is_in_use_at_the_commit_and_left_intact()
    {
        FileStream? player = null;
        try
        {
            var result = await RunAsync(_ => player = new FileStream(_original, FileMode.Open, FileAccess.Read, FileShare.Read));

            Assert.Equal(SwapOutcome.InUse, result.Outcome);
            Assert.Equal("original content", await File.ReadAllTextAsync(_original));
        }
        finally
        {
            player?.Dispose();
        }

        Assert.Equal([Path.Join("Movie (2020)", "Movie (2020).mkv")], FilesInLibrary());
        var swap = SwapRow();
        Assert.Equal("rolled_back", swap.State);
        Assert.False(swap.Committed);
    }

    [WindowsFact("Share modes are a Windows behaviour.")]
    public async Task A_reader_that_shares_delete_does_not_block_the_swap()
    {
        using var reader = new FileStream(_original, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);

        Assert.False(PhysicalSwapFileSystem.Instance.IsInUse(_original));
        var result = await RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.Equal("cleaned content", await File.ReadAllTextAsync(_original));
    }

    [Fact]
    public async Task A_hardlinked_real_file_is_skipped()
    {
        var link = Path.Join(_db.Join("seeding"), "Movie (2020).mkv");
        Directory.CreateDirectory(Path.GetDirectoryName(link)!);
        if (!FileLifecycle.CreateHardLink(link, _original))
        {
            return; // the volume does not support hard links
        }

        Assert.Equal(2, PhysicalSwapFileSystem.Instance.LinkCount(_original));
        var result = await RunAsync();

        Assert.Equal(SwapOutcome.Hardlinked, result.Outcome);
        Assert.Equal("original content", await File.ReadAllTextAsync(link));
        Assert.Equal([Path.Join("Movie (2020)", "Movie (2020).mkv")], FilesInLibrary());
        Assert.False(Payload().ContainsKey("library_swap"));

        File.Delete(link);
        Assert.Equal(1, PhysicalSwapFileSystem.Instance.LinkCount(_original));
    }

    [WindowsFact("The read-only attribute is a Windows behaviour.")]
    public async Task A_read_only_real_file_is_refused()
    {
        File.SetAttributes(_original, FileAttributes.ReadOnly);

        var result = await RunAsync();

        Assert.Equal(SwapOutcome.NotWritable, result.Outcome);
        Assert.Equal("original content", await File.ReadAllTextAsync(_original));
    }

    [Fact]
    public async Task A_real_change_to_the_original_replaces_nothing()
    {
        var result = await RunAsync(_ => File.AppendAllText(_original, " and more"));

        Assert.Equal(SwapOutcome.SourceChanged, result.Outcome);
        Assert.Equal([Path.Join("Movie (2020)", "Movie (2020).mkv")], FilesInLibrary());
        Assert.Equal("original content and more", await File.ReadAllTextAsync(_original));
    }

    [WindowsFact("Access control lists are a Windows behaviour.")]
    public async Task An_explicit_permission_on_the_original_is_carried_to_the_cleaned_file()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        var everyone = new SecurityIdentifier(WellKnownSidType.WorldSid, null);
        var info = new FileInfo(_original);
        var security = info.GetAccessControl();
        security.AddAccessRule(new FileSystemAccessRule(everyone, FileSystemRights.ReadData, AccessControlType.Allow));
        info.SetAccessControl(security);

        var result = await RunAsync();

        Assert.Equal(SwapOutcome.Committed, result.Outcome);
        Assert.Empty(result.Warnings);
        var rules = new FileInfo(_original).GetAccessControl().GetAccessRules(includeExplicit: true, includeInherited: false, typeof(SecurityIdentifier));
        var carried = false;
        foreach (FileSystemAccessRule rule in rules)
        {
            carried |= rule.IdentityReference.Equals(everyone) && rule.FileSystemRights.HasFlag(FileSystemRights.ReadData) && rule.AccessControlType == AccessControlType.Allow;
        }

        Assert.True(carried, "the explicit rule on the original was not carried to the cleaned file");
    }

    [Fact]
    public void A_rename_never_replaces_an_existing_file()
    {
        var other = Path.Join(_library, "other.mkv");
        File.WriteAllText(other, "someone else's file");

        Assert.ThrowsAny<IOException>(() => PhysicalSwapFileSystem.Instance.Move(_original, other));

        Assert.Equal("original content", File.ReadAllText(_original));
        Assert.Equal("someone else's file", File.ReadAllText(other));
    }

    [Fact]
    public void Free_space_is_read_for_a_real_folder()
    {
        Assert.True(PhysicalSwapFileSystem.Instance.AvailableFreeBytes(_library) > 0);
    }

    [Fact]
    public void A_missing_folder_fails_the_write_probe()
    {
        Assert.ThrowsAny<IOException>(() => PhysicalSwapFileSystem.Instance.ProbeWrite(Path.Join(_library, "missing")));
    }

    [Fact]
    public async Task The_real_sweep_recovers_every_case_across_nested_folders_and_leaves_other_files_alone()
    {
        // Interrupted after the original was moved aside: backup present, original missing, temp present.
        var season = Path.Join(_library, "Show", "Season 01");
        Directory.CreateDirectory(season);
        var episode = Path.Join(season, "Show.S01E01.mkv");
        File.WriteAllText(SafeSwapRules.BackupPath(episode), "episode original");
        File.WriteAllText(SafeSwapRules.TempPath(episode), "episode cleaned");

        // Interrupted after the commit: original (cleaned) and backup present.
        File.WriteAllText(_original, "cleaned content");
        File.WriteAllText(Backup, "original content");

        // Interrupted while writing: temp only.
        var other = Path.Join(_library, "Other.mp4");
        File.WriteAllText(other, "other original");
        File.WriteAllText(SafeSwapRules.TempPath(other), "half written");

        var decoy = Path.Join(_library, "Other.weir-tmp-notes.txt");
        File.WriteAllText(decoy, "not Weir's");

        var logger = new ListLogger<SwapRecoverySweep>();
        var report = await new SwapRecoverySweep(PhysicalSwapFileSystem.Instance, _journal, logger).RunAsync([_library], walkFolders: true);

        Assert.Equal(new SwapRecoveryReport(2, 1, 1, 0), report);
        Assert.Equal(
            new[] { "Movie (2020)/Movie (2020).mkv", "Other.mp4", "Other.weir-tmp-notes.txt", "Show/Season 01/Show.S01E01.mkv" }
                .Select(path => path.Replace('/', Path.DirectorySeparatorChar))
                .Order(StringComparer.Ordinal),
            FilesInLibrary());
        Assert.Equal("episode original", await File.ReadAllTextAsync(episode));
        Assert.Equal("cleaned content", await File.ReadAllTextAsync(_original));
        Assert.Equal("other original", await File.ReadAllTextAsync(other));
    }

    [Fact]
    public async Task The_real_sweep_goes_to_journaled_paths_first()
    {
        await _journal.RecordAsync(new SwapJournalEntry(_jobId, _original, SwapJournalState.Committing));
        File.Move(_original, Backup);
        File.WriteAllText(Temp, "cleaned content");

        var report = await new SwapRecoverySweep(PhysicalSwapFileSystem.Instance, _journal, new ListLogger<SwapRecoverySweep>())
            .RunAsync([], walkFolders: false);

        Assert.Equal(new SwapRecoveryReport(1, 0, 1, 0), report);
        Assert.Equal([Path.Join("Movie (2020)", "Movie (2020).mkv")], FilesInLibrary());
        Assert.Equal("original content", await File.ReadAllTextAsync(_original));
        Assert.Equal("recovered", SwapRow().State);
    }
}
