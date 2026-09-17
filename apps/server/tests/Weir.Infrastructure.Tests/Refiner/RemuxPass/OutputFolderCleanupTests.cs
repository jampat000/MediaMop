using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Infrastructure.Tests.Refiner.RemuxPass;

/// <summary>
/// Ported from <c>apps/backend/tests/test_refiner_movie_output_cleanup.py</c> and <c>test_refiner_tv_output_cleanup.py</c>, on real
/// folders with the managers' answers and the job queue stated directly.
/// </summary>
public sealed class OutputFolderCleanupTests : IDisposable
{
    private readonly PassFolders _folders = new();
    private readonly FakeCleanupData _data = new();

    public void Dispose() => _folders.Dispose();

    private OutputFolderCleanup Cleanup(int minAge = 0) => new(_data, TimeProvider.System, NullLogger.Instance, minAge, minAge);

    private static ManagerLibraryTruth Reported(params string[] paths) =>
        new(new ManagerConnection("radarr", "Main", "http://x", "k"), SignalStatus.Reported, paths);

    private static string Str(PyDict output, string key) => PyConvert.Str(output[key]);

    private string MovieOutput(string title = "Title", bool old = true)
    {
        var file = _folders.Out(Path.Join(title, "m.mkv"));
        Directory.CreateDirectory(Path.GetDirectoryName(file)!);
        File.WriteAllText(file, "x");
        if (old)
        {
            File.SetLastWriteTimeUtc(file, DateTime.UtcNow.AddDays(-3));
        }

        return file;
    }

    private Task<PyDict> RunMovie(string finalOutputFile, string relative = "Title/m.mkv", string scope = "movie", int minAge = 0)
    {
        var output = new PyDict();
        var source = _folders.Source(relative);
        return Cleanup(minAge).RunMovieAsync(output, _folders.Runtime(), _folders.Watched, source, finalOutputFile, relative, 1, scope, null, CancellationToken.None)
            .ContinueWith(_ => output, TaskScheduler.Default);
    }

    [Fact]
    public void Relative_paths_are_normalised_for_matching()
    {
        Assert.Equal("foo/bar.mkv", OutputFolderCleanup.NormalizeRelativeForMatch("foo/bar.mkv"));
        Assert.Equal("foo/bar.mkv", OutputFolderCleanup.NormalizeRelativeForMatch(".\\foo\\bar.mkv"));
    }

    [Fact]
    public async Task The_wrong_scope_skips_with_a_plain_reason_and_initialises_every_field()
    {
        var output = await RunMovie(MovieOutput(), scope: "tv");

        Assert.Contains("TV output cleanup is separate", Str(output, "movie_output_folder_skip_reason"), StringComparison.Ordinal);
        Assert.Equal(
            ["movie_output_folder_deleted", "movie_output_folder_path", "movie_output_folder_skip_reason", "movie_output_truth_check", "movie_output_truth_note", "movie_output_age_seconds", "movie_output_cascade_folders_deleted", "movie_output_dry_run"],
            output.Keys);

        var tv = new PyDict();
        await Cleanup().RunTvAsync(tv, _folders.Runtime(), _folders.Watched, _folders.Source("m.mkv"), MovieOutput(), 1, "movie", null, CancellationToken.None);
        Assert.Contains("Movies output-folder cleanup is separate", Str(tv, "tv_output_season_folder_skip_reason"), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_manager_keeping_a_file_inside_the_folder_blocks_the_delete()
    {
        var final = MovieOutput();
        _data.Truth.Add(Reported(final));

        var output = await RunMovie(final);

        Assert.Equal("failed", Str(output, "movie_output_truth_check"));
        Assert.False(((PyBool)output["movie_output_folder_deleted"]).Value);
        Assert.True(File.Exists(final));
    }

    [Fact]
    public async Task Every_manager_clear_and_old_enough_deletes_the_folder_and_its_empty_parents()
    {
        var final = MovieOutput(Path.Join("Collection", "Title"));
        // Confirms this exact release (not merely "no other files sit in this folder"): the manager's own library
        // keeps a file under the same title (file-name stem) elsewhere — this is how a manager that copies on
        // import, rather than leaving the file in place, would record it — alongside an unrelated file.
        _data.Truth.Add(Reported(_folders.Out(Path.Join("ManagerLibrary", "m.mkv")), _folders.Out(Path.Join("Other", "x.mkv"))));

        var output = await RunMovie(final, "Collection/Title/m.mkv");

        Assert.Equal("passed", Str(output, "movie_output_truth_check"));
        Assert.True(((PyBool)output["movie_output_folder_deleted"]).Value);
        Assert.False(Directory.Exists(_folders.Out("Collection")));
        Assert.True(Directory.Exists(_folders.Output));
        Assert.Equal(PyNull.Instance, output["movie_output_folder_skip_reason"]);
        Assert.Single(((PyList)output["movie_output_cascade_folders_deleted"]).Items);
    }

    [Fact]
    public async Task Issue_545_item_1_a_manager_that_has_not_imported_yet_keeps_the_folder()
    {
        // The manager is reachable and answers, but its library does not yet include this release — exactly what
        // "hasn't imported yet" (or "imports by copy and scans later") looks like. Reporting zero files that
        // conflict with the folder must not be read as "safe to delete": nothing here says the manager has this
        // release at all yet.
        var final = MovieOutput(Path.Join("Collection", "Title"));
        _data.Truth.Add(Reported());

        var output = await RunMovie(final, "Collection/Title/m.mkv");

        Assert.Equal("skipped", Str(output, "movie_output_truth_check"));
        Assert.False(((PyBool)output["movie_output_folder_deleted"]).Value);
        Assert.Contains("not yet reported this release as imported", Str(output, "movie_output_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(File.Exists(final));
        Assert.True(Directory.Exists(_folders.Out(Path.Join("Collection", "Title"))));
    }

    [Fact]
    public async Task A_hand_off_the_ledger_already_recorded_as_delivered_needs_no_further_import_evidence()
    {
        // Second way to be "confirmed" (issue #545 item 1): the hand-off ledger already recorded this pass's
        // outcome as delivered to the manager that asked for it, so the "no evidence of import yet" caution does
        // not apply even though the manager's own library listing is still empty.
        var final = MovieOutput(Path.Join("Collection", "Title"));
        _data.Truth.Add(Reported());
        _data.HandoffAcknowledged = true;

        var output = await RunMovie(final, "Collection/Title/m.mkv");

        Assert.Equal("passed", Str(output, "movie_output_truth_check"));
        Assert.True(((PyBool)output["movie_output_folder_deleted"]).Value);
    }

    [Fact]
    public async Task An_unreachable_manager_skips()
    {
        var final = MovieOutput();
        _data.Truth.Add(new ManagerLibraryTruth(new ManagerConnection("radarr", "4K", "http://x", "k"), SignalStatus.Unreachable, [], "down"));

        var output = await RunMovie(final);

        Assert.Equal("skipped", Str(output, "movie_output_truth_check"));
        Assert.True(File.Exists(final));
    }

    [Fact]
    public async Task The_age_gate_blocks_a_recently_changed_folder()
    {
        var final = MovieOutput(old: false);
        _data.Truth.Add(Reported());

        var output = await RunMovie(final, minAge: 3600);

        Assert.Contains("changed too recently", Str(output, "movie_output_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(File.Exists(final));
    }

    [Fact]
    public async Task Another_movie_pass_for_the_same_file_blocks_but_a_tv_pass_does_not()
    {
        var final = MovieOutput();
        _data.Truth.Add(Reported(_folders.Out(Path.Join("ManagerLibrary", "m.mkv"))));
        _data.ActiveJobs.Add(new ActiveRemuxJob(2, """{"relative_media_path":"Title\\m.mkv","media_scope":"tv"}"""));
        _data.ActiveJobs.Add(new ActiveRemuxJob(1, """{"relative_media_path":"Title/m.mkv","media_scope":"movie"}"""));

        var unblocked = await RunMovie(final);
        Assert.True(((PyBool)unblocked["movie_output_folder_deleted"]).Value);

        final = MovieOutput();
        _data.ActiveJobs.Add(new ActiveRemuxJob(3, """{"relative_media_path":"./Title/m.mkv"}"""));
        var blocked = await RunMovie(final);
        Assert.Contains("Another Movies video pass", Str(blocked, "movie_output_folder_skip_reason"), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_file_at_the_output_root_or_outside_it_skips()
    {
        var atRoot = _folders.Out("m.mkv");
        File.WriteAllText(atRoot, "x");
        Assert.Contains("directly in the Movies output folder root", Str(await RunMovie(atRoot, "m.mkv"), "movie_output_folder_skip_reason"), StringComparison.Ordinal);

        var outside = Path.Join(_folders.Root, "elsewhere", "m.mkv");
        Assert.Contains("outside the Movies output folder", Str(await RunMovie(outside), "movie_output_folder_skip_reason"), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_locked_folder_is_reported_and_left()
    {
        var final = MovieOutput();
        _data.Truth.Add(Reported(_folders.Out(Path.Join("ManagerLibrary", "m.mkv"))));
        PyDict output;
        using (new FileStream(final, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            output = await RunMovie(final);
        }

        if (OperatingSystem.IsWindows())
        {
            Assert.Contains("could not remove the movie output folder", Str(output, "movie_output_folder_skip_reason"), StringComparison.Ordinal);
            Assert.Equal("skipped", Str(output, "movie_output_truth_check"));
            Assert.True(File.Exists(final));
        }
    }

    [Fact]
    public async Task Tv_deletes_the_season_by_its_direct_child_episodes_and_cascades_the_show()
    {
        var episode = _folders.Out(Path.Join("Show", "S01", "ep.mkv"));
        Directory.CreateDirectory(Path.GetDirectoryName(episode)!);
        File.WriteAllText(episode, "x");
        File.SetLastWriteTimeUtc(episode, DateTime.UtcNow.AddDays(-3));
        var nested = _folders.Out(Path.Join("Show", "S01", "extras", "new.mkv"));
        Directory.CreateDirectory(Path.GetDirectoryName(nested)!);
        File.WriteAllText(nested, "fresh");
        _data.Truth.Add(Reported(_folders.Out(Path.Join("ManagerLibrary", "ep.mkv"))));
        var output = new PyDict();

        await Cleanup(minAge: 3600).RunTvAsync(output, _folders.Runtime(), _folders.Watched, _folders.Source(Path.Join("Show", "S01", "ep.mkv")), episode, 1, "tv", null, CancellationToken.None);

        Assert.True(((PyBool)output["tv_output_season_folder_deleted"]).Value, PyJsonWriter.Dumps(output, PyJsonFormat.Compact));
        Assert.False(Directory.Exists(_folders.Out("Show")));
    }

    [Fact]
    public async Task Tv_skips_without_direct_child_episodes_or_with_another_pass_for_the_season()
    {
        var episode = _folders.Out(Path.Join("Show", "S01", "ep.mkv"));
        Directory.CreateDirectory(Path.GetDirectoryName(episode)!);
        _data.Truth.Add(Reported());
        var empty = new PyDict();
        await Cleanup().RunTvAsync(empty, _folders.Runtime(), _folders.Watched, _folders.Source(Path.Join("Show", "S01", "ep.mkv")), episode, 1, "tv", null, CancellationToken.None);
        Assert.Contains("did not find any supported episode media file", Str(empty, "tv_output_season_folder_skip_reason"), StringComparison.Ordinal);

        File.WriteAllText(episode, "x");
        _data.ActiveJobs.Add(new ActiveRemuxJob(7, """{"relative_media_path":"Show/S01/ep2.mkv","media_scope":"tv"}"""));
        var blocked = new PyDict();
        await Cleanup().RunTvAsync(blocked, _folders.Runtime(), _folders.Watched, _folders.Source(Path.Join("Show", "S01", "ep.mkv")), episode, 1, "tv", null, CancellationToken.None);
        Assert.Contains("Another TV video pass", Str(blocked, "tv_output_season_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(File.Exists(episode));
    }
}
