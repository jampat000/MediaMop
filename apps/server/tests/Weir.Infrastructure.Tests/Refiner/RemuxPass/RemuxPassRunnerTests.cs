using System.Text;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Rules;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;
using Weir.Infrastructure.Refiner.RemuxPass;
using Weir.Infrastructure.Tests.Media;

namespace Weir.Infrastructure.Tests.Refiner.RemuxPass;

/// <summary>
/// A process runner standing in for ffprobe and ffmpeg: probes answer from a table keyed by file name, a remux writes its output
/// file, and every call is recorded.
/// </summary>
internal sealed class FakeMediaRunner : IProcessRunner
{
    // #500: every stream carries its own "duration" matching the format's, so the staged-output validation's
    // expected-duration-from-kept-streams check has an answer without needing to fall back to measuring the
    // (fake) source directly.
    public const string EnglishOnly =
        """{"format":{"duration":"100.0"},"streams":[{"index":0,"codec_type":"video","codec_name":"h264","width":1920,"height":1080,"duration":"100.0"},{"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"},"disposition":{"default":1},"duration":"100.0"}]}""";

    public const string EnglishAndJapanese =
        """{"format":{"duration":"100.0"},"streams":[{"index":0,"codec_type":"video","codec_name":"h264","duration":"100.0"},{"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"},"disposition":{"default":1},"duration":"100.0"},{"index":2,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"jpn"},"duration":"100.0"}]}""";

    public Dictionary<string, string> Probes { get; } = new(StringComparer.OrdinalIgnoreCase);

    public string DefaultProbe { get; set; } = EnglishOnly;

    public string? ProbeError { get; set; }

    public string? RemuxError { get; set; }

    public string? IntegrityError { get; set; }

    public IReadOnlyList<string> ProgressLines { get; set; } = ["out_time_ms=25000000", "speed=2x", "progress=continue", "progress=end"];

    public List<IReadOnlyList<string>> Calls { get; } = [];

    public IEnumerable<IReadOnlyList<string>> Probed => Calls.Where(argv => argv[0] == "ffprobe");

    public IEnumerable<IReadOnlyList<string>> Remuxes => Calls.Where(argv => argv[0] == "ffmpeg" && argv.Contains("-map") && !argv.Contains("null"));

    public Task<ProcessResult> RunAsync(ProcessRequest request, CancellationToken cancellationToken = default)
    {
        var argv = request.Argv;
        lock (Calls)
        {
            Calls.Add(argv);
        }

        if (argv[0] == "ffprobe")
        {
            if (ProbeError is not null)
            {
                return Result(1, stderr: ProbeError);
            }

            var name = Path.GetFileName(argv[^1]);
            return Result(0, stdout: Probes.TryGetValue(name, out var json) ? json : DefaultProbe);
        }

        if (argv.Contains("-hwaccels"))
        {
            return Result(0, stdout: "Hardware acceleration methods:\n");
        }

        if (argv.Contains("null"))
        {
            return IntegrityError is null ? Result(0) : Result(1, stderr: IntegrityError);
        }

        if (RemuxError is not null)
        {
            return Result(1, stderr: RemuxError);
        }

        File.WriteAllBytes(argv[^1], new byte[64]);
        foreach (var line in ProgressLines)
        {
            request.OnStdoutLine?.Invoke(line);
        }

        return Result(0);
    }

    private static Task<ProcessResult> Result(int exitCode, string stdout = "", string stderr = "") =>
        Task.FromResult(new ProcessResult { ExitCode = exitCode, Stdout = Encoding.UTF8.GetBytes(stdout), Stderr = Encoding.UTF8.GetBytes(stderr) });
}

internal sealed class RecordingFacts : IRemuxPassFileFacts
{
    public List<MeasuredMediaFacts> Measured { get; } = [];

    public List<CollisionDecision> Collisions { get; } = [];

    public Task RecordMeasuredMediaFactsAsync(MeasuredMediaFacts facts, CancellationToken cancellationToken)
    {
        Measured.Add(facts);
        return Task.CompletedTask;
    }

    public List<long?> CollisionLibraryIds { get; } = [];

    public Task RecordOutputCollisionAsync(string relativePath, CollisionDecision decision, long? libraryId, CancellationToken cancellationToken)
    {
        Collisions.Add(decision);
        CollisionLibraryIds.Add(libraryId);
        return Task.CompletedTask;
    }
}

internal sealed class FakeCleanupData : IPostSuccessCleanupData
{
    public List<ManagerLibraryTruth> Truth { get; } = [];

    public List<ActiveRemuxJob> ActiveJobs { get; } = [];

    public bool HandoffAcknowledged { get; set; }

    public Task<IReadOnlyList<ManagerLibraryTruth>> CollectLibraryTruthAsync(string mediaScope, CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<ManagerLibraryTruth>>(Truth);

    public Task<IReadOnlyList<ActiveRemuxJob>> ActiveRemuxJobsAsync(CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<ActiveRemuxJob>>(ActiveJobs);

    public Task<bool> HandoffOutcomeAcknowledgedAsync(HandoffOrigin? origin, CancellationToken cancellationToken) =>
        Task.FromResult(HandoffAcknowledged);
}

internal sealed class FakeOriginalLanguage : IOriginalLanguageLookup
{
    public LookupResult Answer { get; set; } = new() { Status = LookupResult.StatusNotConfigured, Detail = "no metadata provider is configured" };

    public List<(string Scope, string Path, HandoffOrigin? Origin)> Asked { get; } = [];

    public Task<LookupResult> LookupAsync(string mediaScope, string relativeMediaPath, HandoffOrigin? origin, CancellationToken cancellationToken)
    {
        Asked.Add((mediaScope, relativeMediaPath, origin));
        return Task.FromResult(Answer);
    }
}

/// <summary>A fact that runs only on Windows, for share-mode, hard-link and mandatory-lock behaviour.</summary>
[AttributeUsage(AttributeTargets.Method)]
internal sealed class WindowsFactAttribute : FactAttribute
{
    public WindowsFactAttribute(string reason)
    {
        if (!OperatingSystem.IsWindows())
        {
            Skip = reason;
        }
    }
}

/// <summary>Real folders for one pass: watched, output and a custom work folder.</summary>
internal sealed class PassFolders : IDisposable
{
    private readonly TempDirectory _root = new();

    public PassFolders()
    {
        Watched = Directory.CreateDirectory(_root.Join("media")).FullName;
        Output = Directory.CreateDirectory(_root.Join("out")).FullName;
        Work = Directory.CreateDirectory(_root.Join("work")).FullName;
    }

    public string Root => _root.Path;

    public string Watched { get; }

    public string Output { get; }

    public string Work { get; }

    public string Source(string relative, int bytes = 2000)
    {
        var path = Path.Join(Watched, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllBytes(path, Enumerable.Repeat((byte)'x', bytes).ToArray());
        return path;
    }

    public string Out(string relative) => Path.Join(Output, relative);

    public RefinerPathRuntime Runtime(bool workIsDefault = false, string collision = "replace", string sidecars = "") => new()
    {
        WatchedFolder = Watched,
        OutputFolder = Output,
        WorkFolderEffective = Work,
        WorkFolderIsDefault = workIsDefault,
        OutputCollisionPolicy = collision,
        SidecarPatternsCsv = sidecars,
    };

    public void Dispose() => _root.Dispose();
}

/// <summary>
/// Ported from <c>apps/backend/tests/test_refiner_file_remux_pass_run.py</c> on real temporary folders, with ffprobe and ffmpeg
/// replaced by a fake process runner rather than by patching the pass.
/// </summary>
public sealed class RemuxPassRunnerTests : IDisposable
{
    private readonly PassFolders _folders = new();
    private readonly FakeMediaRunner _media = new();
    private readonly RecordingFacts _facts = new();
    private readonly FakeCleanupData _cleanup = new();
    private readonly FakeOriginalLanguage _language = new();
    private readonly List<PyDict> _progress = [];

    public void Dispose() => _folders.Dispose();

    private RemuxPassRunner Runner(bool? hardlink = null, Func<string, long>? freeBytes = null) =>
        new(
            new MediaTools(_media, new FixedResolver(), new ListLogger<MediaTools>(), TimeProvider.System),
            new FixedResolver(),
            _facts,
            _cleanup,
            new SkippedTvSeasonFolderCleanup(),
            _language,
            new RemuxPassSettings { WatchedFolderMinFileAgeSeconds = 0, MovieOutputCleanupMinAgeSeconds = 0, TvOutputCleanupMinAgeSeconds = 0 },
            TimeProvider.System,
            NullLogger<RemuxPassRunner>.Instance)
        {
            HardlinkFastPathSupported = hardlink ?? OperatingSystem.IsWindows(),
            FreeBytes = freeBytes,
        };

    private Task<PyDict> Run(
        string relative,
        RefinerPathRuntime? runtime = null,
        long minSizeMb = 0,
        bool passThrough = false,
        string scope = "movie",
        long? minAge = 0,
        RefinerRulesConfig? rules = null,
        long minimumFreeMb = 0,
        RemuxPassRunner? runner = null) =>
        (runner ?? Runner()).RunAsync(new RemuxPassRequest
        {
            Runtime = runtime ?? _folders.Runtime(),
            RelativeMediaPath = relative,
            MinInputFileSizeMb = minSizeMb,
            PassThroughUnchanged = passThrough,
            MediaScope = scope,
            MinFileAgeSeconds = minAge,
            RulesConfig = rules,
            MinimumFreeDiskSpaceMb = minimumFreeMb,
            CurrentJobId = 1,
            ProgressReporter = _progress.Add,
        });

    private static string Str(PyDict result, string key) => PyConvert.Str(result[key]);

    private static bool? Bool(PyDict result, string key) => result.Get(key) is PyBool value ? value.Value : null;

    [Fact]
    public async Task A_missing_watched_folder_fails_before_execution()
    {
        var result = await Run("x.mkv", _folders.Runtime() with { WatchedFolder = Path.Join(_folders.Root, "nope") });

        Assert.False(Bool(result, "ok"));
        Assert.Equal(RemuxPassOutcomes.FailedBeforeExecution, Str(result, "outcome"));
        Assert.Equal("failed", Str(result, "preflight_status"));
        Assert.Contains("watched folder", Str(result, "reason").ToLowerInvariant(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_missing_file_and_an_unsupported_type_are_explained()
    {
        var missing = await Run("Missing/film.mkv");
        Assert.Contains("could not find this file", Str(missing, "reason").ToLowerInvariant(), StringComparison.Ordinal);
        Assert.Contains("restore the file", Str(missing, "reason").ToLowerInvariant(), StringComparison.Ordinal);

        File.WriteAllText(Path.Join(_folders.Watched, "notes.txt"), "not media");
        var text = await Run("notes.txt");
        Assert.Contains("does not process .txt files", Str(text, "reason"), StringComparison.Ordinal);
        Assert.Contains("supported media file", Str(text, "reason"), StringComparison.Ordinal);
        Assert.Empty(_media.Calls);
    }

    [Fact]
    public async Task An_audio_only_file_with_a_video_extension_is_rejected_before_writing()
    {
        _folders.Source("audio-disguised-as-video.mpg");
        _media.DefaultProbe = """{"streams":[{"index":0,"codec_type":"audio","codec_name":"ac3","channels":2}]}""";

        var result = await Run("audio-disguised-as-video.mpg");

        Assert.False(Bool(result, "ok"));
        Assert.Equal(RemuxPassOutcomes.FailedBeforeExecution, Str(result, "outcome"));
        Assert.Contains("contain a video stream", Str(result, "reason"), StringComparison.Ordinal);
        Assert.Equal("no_video_stream", Str(result, "rejection_kind"));
        Assert.Equal(_folders.Watched, Str(result, "refiner_watched_folder_resolved"));
        Assert.Empty(_media.Remuxes);
        Assert.False(File.Exists(_folders.Out("audio-disguised-as-video.mpg")));
        // The keys in the reference's order: extras first, then the inspected path.
        Assert.Equal(["ok", "outcome", "preflight_status", "preflight_reason", "reason", "relative_media_path", "rejection_kind", "media_scope", "refiner_watched_folder_resolved", "inspected_source_path"], result.Keys);
    }

    [WindowsFact("Share-mode writer detection is Windows semantics.")]
    public async Task Another_program_writing_the_source_makes_the_pass_wait_without_probing()
    {
        var source = _folders.Source("downloading.mkv");
        using (new FileStream(source, FileMode.Open, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete))
        {
            var result = await Run("downloading.mkv");

            Assert.False(Bool(result, "ok"));
            Assert.Equal(RemuxPassOutcomes.SourceNotReady, Str(result, "outcome"));
            Assert.True(Bool(result, "retryable_wait"));
            Assert.Contains("still open for writing", Str(result, "reason"), StringComparison.Ordinal);
        }

        Assert.Empty(_media.Probed);
        Assert.False(File.Exists(_folders.Out("downloading.mkv")));
    }

    [Fact]
    public async Task A_file_needing_no_remux_is_placed_in_the_output_and_its_release_folder_removed()
    {
        var source = _folders.Source(Path.Join("ReleaseTitle", "one.mkv"));

        var result = await Run("ReleaseTitle/one.mkv");

        Assert.True(Bool(result, "ok"));
        Assert.Equal(RemuxPassOutcomes.LiveSkippedNotRequired, Str(result, "outcome"));
        Assert.Equal("ok", Str(result, "preflight_status"));
        Assert.False(Bool(result, "live_mutations_skipped"));
        Assert.True(Bool(result, "output_copied_without_remux"));
        Assert.Equal(OperatingSystem.IsWindows() ? "validated_hardlink" : "validated_copy", Str(result, "unchanged_output_method"));
        Assert.Equal(Path.GetFullPath(_folders.Out(Path.Join("ReleaseTitle", "one.mkv"))), Str(result, "output_file"));
        Assert.Equal(2000, new FileInfo(_folders.Out(Path.Join("ReleaseTitle", "one.mkv"))).Length);
        Assert.True(Bool(result, "source_deleted_after_success"));
        Assert.True(Bool(result, "source_folder_deleted"));
        Assert.False(File.Exists(source));
        Assert.False(Directory.Exists(Path.Join(_folders.Watched, "ReleaseTitle")));
        Assert.Empty(_media.Remuxes);
        var measured = Assert.Single(_facts.Measured);
        Assert.Equal((1920L, 1080L, "h264", 1L, 0L, 100.0), (measured.VideoWidth!.Value, measured.VideoHeight!.Value, measured.VideoCodec, measured.AudioTrackCount!.Value, measured.SubtitleTrackCount!.Value, measured.DurationSeconds!.Value));
        Assert.Equal("write", Assert.Single(_facts.Collisions).Action);
        // #539 item 5: the integrity read runs on every platform, Windows included.
        Assert.Contains(_media.Calls, argv => argv.Contains("null"));
        Assert.Equal("{\"device\"", PyJsonWriter.Dumps(result["source_fingerprint"], PyJsonFormat.Compact)[..9]);
    }

    [Fact]
    public async Task Operator_pass_through_keeps_foreign_audio_and_ignores_the_size_guardrail()
    {
        var source = _folders.Source(Path.Join("ForeignLanguageFilm", "film.mkv"), 4400);
        _media.DefaultProbe =
            """{"format":{"duration":"7200"},"streams":[{"index":0,"codec_type":"video","codec_name":"h264","duration":"7200"},{"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"fra"},"disposition":{"default":1},"duration":"7200"}]}""";

        var result = await Run("ForeignLanguageFilm/film.mkv", minSizeMb: 999, passThrough: true);

        Assert.True(Bool(result, "ok"));
        Assert.Equal(RemuxPassOutcomes.LiveSkippedNotRequired, Str(result, "outcome"));
        Assert.True(Bool(result, "pass_through_unchanged"));
        Assert.True(Bool(result, "output_copied_without_remux"));
        Assert.Equal(4400, new FileInfo(_folders.Out(Path.Join("ForeignLanguageFilm", "film.mkv"))).Length);
        Assert.True(Bool(result, "source_deleted_after_success"));
        Assert.Contains(_progress, update => update.Get("percent") is PyFloat { Value: 100.0 });
        Assert.Contains(_progress, update => PyConvert.Str(update.Get("message") ?? PyNull.Instance).Contains("passing this file through unchanged", StringComparison.Ordinal));
        Assert.False(File.Exists(source));
        Assert.Equal("[]", PyJsonWriter.Dumps(result["ffmpeg_argv"], PyJsonFormat.Compact));
        Assert.Contains("operator bypassed Refiner rules", Str(result, "reason"), StringComparison.Ordinal);
    }

    [WindowsFact("The hard-link fast path is Windows only.")]
    public async Task A_surviving_watched_source_detaches_a_hard_linked_output()
    {
        var source = _folders.Source("root.mkv", 1000);

        var result = await Run("root.mkv");

        Assert.True(Bool(result, "ok"));
        Assert.False(Bool(result, "source_folder_deleted"));
        Assert.True(File.Exists(source));
        Assert.Equal("validated_hardlink_detached_copy", Str(result, "unchanged_output_method"));
        File.WriteAllText(source, "changed later");
        Assert.Equal(1000, new FileInfo(_folders.Out("root.mkv")).Length);
    }

    [Fact]
    public async Task An_existing_output_is_replaced_before_cleanup()
    {
        _folders.Source(Path.Join("ReleaseTitle", "one.mkv"), 10_000);
        Directory.CreateDirectory(_folders.Out("ReleaseTitle"));
        File.WriteAllText(_folders.Out(Path.Join("ReleaseTitle", "one.mkv")), "tiny");

        var result = await Run("ReleaseTitle/one.mkv");

        Assert.True(Bool(result, "ok"));
        Assert.True(Bool(result, "output_replaced_existing"));
        Assert.Equal(10_000, new FileInfo(_folders.Out(Path.Join("ReleaseTitle", "one.mkv"))).Length);
        Assert.True(Bool(result, "source_folder_deleted"));
        Assert.Equal("passed", Str(result, "output_completeness_check"));
        Assert.False(result.ContainsKey("tv_season_folder_deleted"));
        Assert.False(result.ContainsKey("tv_output_season_folder_deleted"));
        Assert.True(result.ContainsKey("movie_output_truth_check"));
    }

    [Fact]
    public async Task An_ffmpeg_failure_is_reported_during_execution_and_keeps_the_source()
    {
        var source = _folders.Source("one.mkv");
        _media.DefaultProbe = FakeMediaRunner.EnglishAndJapanese;
        _media.RemuxError = "ffmpeg simulated failure";

        var result = await Run("one.mkv");

        Assert.False(Bool(result, "ok"));
        Assert.Equal(RemuxPassOutcomes.FailedDuringExecution, Str(result, "outcome"));
        Assert.Equal("ok", Str(result, "preflight_status"));
        Assert.Contains("ffmpeg simulated failure", Str(result, "reason"), StringComparison.Ordinal);
        Assert.True(result.ContainsKey("plan_summary"));
        Assert.True(File.Exists(source));
        Assert.Equal("failed", Str(_progress[^1], "status"));
        Assert.Empty(Directory.EnumerateFiles(_folders.Work));
    }

    [Fact]
    public async Task A_remux_writes_nested_output_notes_the_replacement_and_reports_progress()
    {
        var source = _folders.Source(Path.Join("sub", "d", "deep.mkv"));
        _media.DefaultProbe = FakeMediaRunner.EnglishAndJapanese;
        _media.Probes["deep.mkv"] = FakeMediaRunner.EnglishAndJapanese;
        Directory.CreateDirectory(_folders.Out(Path.Join("sub", "d")));
        File.WriteAllText(_folders.Out(Path.Join("sub", "d", "deep.mkv")), "old");
        _media.DefaultProbe = FakeMediaRunner.EnglishOnly;

        var result = await Run("sub/d/deep.mkv");

        Assert.True(Bool(result, "ok"), PyJsonWriter.Dumps(result, PyJsonFormat.Compact));
        Assert.Equal(RemuxPassOutcomes.LiveOutputWritten, Str(result, "outcome"));
        Assert.True(Bool(result, "output_replaced_existing"));
        Assert.True(result.ContainsKey("output_replacement_note"));
        Assert.Equal(Path.GetFullPath(_folders.Out(Path.Join("sub", "d", "deep.mkv"))), Str(result, "output_file"));
        Assert.Equal(64, new FileInfo(_folders.Out(Path.Join("sub", "d", "deep.mkv"))).Length);
        Assert.False(File.Exists(source));
        Assert.True(Bool(result, "source_deleted_after_success"));
        Assert.True(Bool(result, "source_folder_deleted"));
        Assert.Equal(["processing", "processing", "processing", "finishing", "finished"], _progress.Select(update => Str(update, "status")));
        Assert.Equal(25.0, ((PyFloat)_progress[1]["percent"]).Value);
        Assert.Equal(100.0, ((PyFloat)_progress[^1]["percent"]).Value);
        Assert.Single(((PyList)result["removed_audio"]).Items);
        Assert.Contains("audio out: #1 eng", Str(result, "plan_summary"), StringComparison.Ordinal);
        Assert.Empty(Directory.EnumerateFiles(_folders.Work));
        Assert.Equal(["ok", "outcome", "relative_media_path", "inspected_source_path", "refiner_watched_folder_resolved", "stream_counts"], result.Keys.Take(6));
    }

    [Fact]
    public async Task Hardware_flags_decided_for_the_pass_reach_the_executed_ffmpeg()
    {
        _folders.Source("one.mkv");
        _media.DefaultProbe = FakeMediaRunner.EnglishAndJapanese;
        _media.Probes.Clear();
        var runtime = _folders.Runtime() with { FfmpegStrictness = "experimental" };

        var result = await Run("one.mkv", runtime, runner: Runner());
        _media.DefaultProbe = FakeMediaRunner.EnglishOnly;

        var executed = Assert.Single(_media.Remuxes);
        var recorded = ((PyList)result["ffmpeg_argv"]).Items.Select(PyConvert.Str).ToList();
        Assert.Equal(recorded.TakeWhile(arg => arg != "-i"), executed.TakeWhile(arg => arg != "-i"));
    }

    [Fact]
    public async Task A_truncated_source_waits_instead_of_being_processed()
    {
        _folders.Source("one.mkv");
        _media.IntegrityError = "[matroska,webm @ 0x1] File ended prematurely";

        var result = await Run("one.mkv");

        Assert.Equal(RemuxPassOutcomes.SourceNotReady, Str(result, "outcome"));
        Assert.True(Bool(result, "retryable_wait"));
        Assert.False(File.Exists(_folders.Out("one.mkv")));
    }

    [Fact]
    public async Task Unreadable_content_is_marked_as_evidence_of_a_bad_release()
    {
        _folders.Source("bad.mkv");
        _media.ProbeError = "[matroska,webm @ 0x1] EBML header parsing failed\nbad.mkv: Invalid data found when processing input";

        var result = await Run("bad.mkv");

        Assert.Equal(RemuxPassOutcomes.FailedBeforeExecution, Str(result, "outcome"));
        Assert.True(Bool(result, "content_unusable"));
        Assert.StartsWith("Weir could not read this file's contents, so the file itself looks damaged:", Str(result, "reason"), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Tv_scope_runs_the_tv_cleanups_and_never_the_movie_ones()
    {
        var episode = _folders.Source(Path.Join("Show", "S01", "ep.mkv"), 400);
        Directory.CreateDirectory(_folders.Out(Path.Join("Show", "S01")));
        // #545 item 1: a manager clears the folder only once it has positive evidence of this release (here, the
        // same title kept at its own separate library path) — not merely because it reports no files sitting in
        // the folder being considered (which would equally describe "hasn't imported yet").
        _cleanup.Truth.Add(new ManagerLibraryTruth(
            new ManagerConnection("sonarr", "Main", "http://x", "k"), SignalStatus.Reported, [_folders.Out(Path.Join("ManagerLibrary", "ep.mkv"))]));

        var result = await Run("Show/S01/ep.mkv", scope: "tv");

        Assert.True(Bool(result, "ok"));
        Assert.False(Bool(result, "tv_season_folder_deleted"));
        Assert.Equal(SkippedTvSeasonFolderCleanup.SkipReason, Str(result, "tv_season_folder_skip_reason"));
        Assert.True(File.Exists(episode));
        Assert.True(Bool(result, "tv_output_season_folder_deleted"));
        Assert.False(Directory.Exists(_folders.Out(Path.Join("Show", "S01"))));
        Assert.False(Directory.Exists(_folders.Out("Show")));
        Assert.False(result.ContainsKey("movie_output_folder_deleted"));
        Assert.False(result.ContainsKey("movie_output_truth_check"));
        Assert.False(result.ContainsKey("source_folder_deleted"));
    }

    [Fact]
    public async Task Issue_545_item_1_a_manager_that_has_not_imported_yet_keeps_the_season_folder()
    {
        // The manager answers (it is reachable and reporting), but its own library listing does not yet include
        // this release — exactly what a manager that has not scanned or finished importing yet looks like. Reporting
        // zero *conflicting* files inside the folder must not, by itself, be read as "safe to delete".
        var episode = _folders.Source(Path.Join("Show", "S01", "ep.mkv"), 400);
        Directory.CreateDirectory(_folders.Out(Path.Join("Show", "S01")));
        _cleanup.Truth.Add(new ManagerLibraryTruth(new ManagerConnection("sonarr", "Main", "http://x", "k"), SignalStatus.Reported, []));

        var result = await Run("Show/S01/ep.mkv", scope: "tv");

        Assert.True(Bool(result, "ok"));
        Assert.False(Bool(result, "tv_output_season_folder_deleted"));
        Assert.Contains("not yet reported this release as imported", Str(result, "tv_output_season_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(File.Exists(episode));
        Assert.True(Directory.Exists(_folders.Out(Path.Join("Show", "S01"))));
    }

    [Fact]
    public async Task Issue_545_item_1_a_manager_that_renamed_the_release_on_import_still_confirms_it()
    {
        // A manager that renames on import (a common *arr pattern) will not report the exact output path Weir wrote,
        // but the same title (file-name stem) shows up at a different path — that is still positive evidence.
        _folders.Source(Path.Join("ReleaseTitle", "movie.mkv"), 400);
        Directory.CreateDirectory(_folders.Out("ReleaseTitle"));
        _cleanup.Truth.Add(new ManagerLibraryTruth(
            new ManagerConnection("radarr", "Main", "http://x", "k"), SignalStatus.Reported, [_folders.Out(Path.Join("Renamed", "movie.mkv"))]));

        var result = await Run("ReleaseTitle/movie.mkv");

        Assert.True(Bool(result, "ok"));
        Assert.True(Bool(result, "movie_output_folder_deleted"));
        Assert.False(Directory.Exists(_folders.Out("ReleaseTitle")));
    }

    [Fact]
    public async Task A_video_directly_under_the_watched_root_keeps_its_folder()
    {
        var source = _folders.Source("root.mkv", 500);
        File.WriteAllBytes(_folders.Out("root.mkv"), new byte[100]);

        var result = await Run("root.mkv", runner: Runner(hardlink: false));

        Assert.True(Bool(result, "ok"));
        Assert.False(Bool(result, "source_folder_deleted"));
        Assert.Contains("directly in the watched folder root", Str(result, "source_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(File.Exists(source));
    }

    [WindowsFact("Needs Windows' mandatory file locks.")]
    public async Task A_locked_release_folder_is_left_in_place_with_a_reason()
    {
        _folders.Source(Path.Join("X", "a.mkv"), 600);
        var locked = Path.Join(_folders.Watched, "X", "zz-locked.nfo");
        File.WriteAllText(locked, "nfo");
        PyDict result;
        using (new FileStream(locked, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            result = await Run("X/a.mkv", runner: Runner(hardlink: false));
        }

        Assert.True(Bool(result, "ok"));
        Assert.False(Bool(result, "source_folder_deleted"));
        Assert.False(Bool(result, "source_deleted_after_success"));
        Assert.Contains("could not remove the release folder", Str(result, "source_folder_skip_reason"), StringComparison.Ordinal);
        Assert.True(File.Exists(locked));
    }

    [Fact]
    public async Task A_preflight_failure_carries_no_cleanup_or_argv_fields()
    {
        _folders.Source("bad.mkv", 100);
        _media.ProbeError = "probe failure";

        var probeFailure = await Run("bad.mkv");

        Assert.Equal(RemuxPassOutcomes.FailedBeforeExecution, Str(probeFailure, "outcome"));
        Assert.Contains("ffprobe failed", Str(probeFailure, "preflight_reason"), StringComparison.Ordinal);
        foreach (var key in new[] { "source_deleted_after_success", "source_folder_deleted", "movie_output_folder_deleted", "tv_output_season_folder_deleted", "output_file", "ffmpeg_argv" })
        {
            Assert.False(probeFailure.ContainsKey(key), key);
        }

        _folders.Source("young.mkv", 200);
        var young = await Run("young.mkv", minAge: 999_999);
        Assert.Equal("failed", Str(young, "preflight_status"));
        Assert.Contains("too recently", Str(young, "preflight_reason"), StringComparison.Ordinal);
        Assert.False(young.ContainsKey("source_folder_deleted"));
    }

    [Fact]
    public async Task The_default_work_folder_is_created_when_needed()
    {
        _folders.Source(Path.Join("R", "one.mkv"), 800);
        _media.Probes["one.mkv"] = FakeMediaRunner.EnglishAndJapanese;
        var work = Path.Join(_folders.Root, "home", "refiner", "work");

        var result = await Run("R/one.mkv", _folders.Runtime(workIsDefault: true) with { WorkFolderEffective = work });

        Assert.True(Bool(result, "ok"), PyJsonWriter.Dumps(result, PyJsonFormat.Compact));
        Assert.True(Directory.Exists(work));
        Assert.True(Bool(result, "source_folder_deleted"));

        var custom = await Run("R2/one.mkv", _folders.Runtime() with { WorkFolderEffective = Path.Join(_folders.Root, "no-work") });
        Assert.Contains("could not find this file", Str(custom, "reason"), StringComparison.Ordinal);
    }

    [Fact]
    public async Task The_size_guardrail_skips_before_ffprobe_and_allows_a_file_at_the_minimum()
    {
        var tiny = _folders.Source("tiny.mkv", 1024);
        var skipped = await Run("tiny.mkv", minSizeMb: 1);
        Assert.True(Bool(skipped, "ok"));
        Assert.Equal(RemuxPassOutcomes.SkippedGuardrail, Str(skipped, "outcome"));
        Assert.Equal("skipped", Str(skipped, "preflight_status"));
        Assert.Contains("file below minimum size", Str(skipped, "reason"), StringComparison.Ordinal);
        Assert.Equal("Skipped: file below minimum size (0.0 MB < 1 MB).", Str(skipped, "reason"));
        Assert.True(File.Exists(tiny));
        Assert.Empty(_media.Probed);

        _folders.Source("ok.mkv", 1024 * 1024);
        var allowed = await Run("ok.mkv", minSizeMb: 1);
        Assert.Equal(RemuxPassOutcomes.LiveSkippedNotRequired, Str(allowed, "outcome"));
        Assert.True(File.Exists(_folders.Out("ok.mkv")));
    }

    [Fact]
    public async Task Low_output_disk_space_skips_before_the_unchanged_copy()
    {
        var source = _folders.Source("copy.mkv", 1024 * 1024);

        var result = await Run("copy.mkv", minimumFreeMb: 5120, runner: Runner(freeBytes: _ => 100L * 1024 * 1024));

        Assert.True(Bool(result, "ok"));
        Assert.Equal(RemuxPassOutcomes.SkippedGuardrail, Str(result, "outcome"));
        Assert.Equal("minimum_free_disk_space", Str(result, "guardrail"));
        Assert.Contains("insufficient disk space", Str(result, "reason"), StringComparison.Ordinal);
        Assert.True(File.Exists(source));
        Assert.False(File.Exists(_folders.Out("copy.mkv")));
    }

    [Fact]
    public async Task Sidecars_travel_and_the_collision_policy_is_honoured()
    {
        _folders.Source(Path.Join("Film", "film.mkv"));
        File.WriteAllText(Path.Join(_folders.Watched, "Film", "film.en.srt"), "subs");
        Directory.CreateDirectory(_folders.Out("Film"));
        File.WriteAllText(_folders.Out(Path.Join("Film", "film.mkv")), "existing");

        var result = await Run("Film/film.mkv", _folders.Runtime(collision: "keep_both", sidecars: ".srt"));

        Assert.True(Bool(result, "ok"));
        Assert.Equal("keep_both", Str(result, "output_collision_policy"));
        Assert.EndsWith("film (2).mkv", Str(result, "output_file"), StringComparison.Ordinal);
        Assert.Equal("existing", File.ReadAllText(_folders.Out(Path.Join("Film", "film.mkv"))));
        Assert.Equal("subs", File.ReadAllText(_folders.Out(Path.Join("Film", "film (2).en.srt"))));
        Assert.Equal("[\"film (2).en.srt\"]", PyJsonWriter.Dumps(result["sidecars_migrated"], PyJsonFormat.Compact));
    }

    [Fact]
    public async Task Issue_537_item_4_the_original_language_decides_the_kept_audio()
    {
        _folders.Source(Path.Join("Amelie.2001.1080p", "film.mkv"));
        _media.Probes["film.mkv"] =
            """{"streams":[{"index":0,"codec_type":"video","codec_name":"h264","duration":"100.0"},{"index":1,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"eng"},"disposition":{"default":1},"duration":"100.0"},{"index":2,"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"fre"},"duration":"100.0"}]}""";
        // #500: the fake output probe (the temp file's random name never matches a Probes entry, so this is what
        // the staged-output validation sees) must match the plan this scenario actually produces — the French
        // track kept as the sole, default audio.
        _media.DefaultProbe =
            """{"format":{"duration":"100.0"},"streams":[{"codec_type":"video","duration":"100.0"},{"codec_type":"audio","codec_name":"aac","channels":2,"tags":{"language":"fre"},"disposition":{"default":1},"duration":"100.0"}]}""";
        _language.Answer = new LookupResult { Status = LookupResult.StatusMatched, Metadata = new TitleMetadata { OriginalLanguage = "fr", Title = "Amélie", Year = 2001 } };
        var rules = RemuxRules.DefaultConfig() with { OriginalLanguage = new OriginalLanguageRules { Enabled = true } };

        var result = await Run("Amelie.2001.1080p/film.mkv", rules: rules);

        Assert.True(Bool(result, "ok"), PyJsonWriter.Dumps(result, PyJsonFormat.Compact));
        Assert.Equal("movie", Assert.Single(_language.Asked).Scope);
        var executed = Assert.Single(_media.Remuxes);
        Assert.Contains("0:2", executed);
        Assert.DoesNotContain("0:1", executed);
        Assert.Contains("original language (fre)", string.Join(" ", ((PyList)result["audio_selection_notes"]).Items.Select(PyConvert.Str)), StringComparison.Ordinal);
        Assert.Equal("[2]", PyJsonWriter.Dumps(((PyDict)result["original_language"])["preferred_audio_indices"], PyJsonFormat.Compact));

        // Without the option, the preference list (English first) decides and nobody is asked.
        _language.Asked.Clear();
        _media.Calls.Clear();
        _media.DefaultProbe = FakeMediaRunner.EnglishOnly;
        _folders.Source(Path.Join("Amelie.2001.1080p", "film.mkv"));
        var plain = await Run("Amelie.2001.1080p/film.mkv", rules: RemuxRules.DefaultConfig());
        Assert.True(Bool(plain, "ok"), PyJsonWriter.Dumps(plain, PyJsonFormat.Compact));
        Assert.Empty(_language.Asked);
        Assert.Contains("0:1", Assert.Single(_media.Remuxes));
        Assert.False(plain.ContainsKey("original_language"));
    }
}
