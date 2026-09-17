using System.ComponentModel;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Weir.Core.Media;
using Weir.Core.Rules;
using Weir.Infrastructure.Processes;

namespace Weir.Infrastructure.Media;

/// <summary>
/// ffprobe and ffmpeg execution (<c>refiner_remux_mux.py</c> and <c>detect_acceleration</c>): probing, output
/// validation, the full-read integrity check, remuxing with progress, and hardware detection. Decisions live in
/// <see cref="Weir.Core.Media"/>; this class runs the tools and hands their output over.
/// </summary>
public sealed partial class MediaTools
{
    private readonly IProcessRunner _runner;
    private readonly IMediaToolResolver _resolver;
    private readonly ILogger<MediaTools> _logger;
    private readonly TimeProvider _timeProvider;
    private readonly bool _windows = OperatingSystem.IsWindows();
    private readonly Func<string, MediaFileState> _inspectFile;

    public MediaTools(IProcessRunner runner, IMediaToolResolver resolver, ILogger<MediaTools> logger, TimeProvider timeProvider)
        : this(runner, resolver, logger, timeProvider, InspectFile)
    {
    }

    /// <summary>For tests: file state comes from <paramref name="inspectFile"/> instead of the filesystem.</summary>
    internal MediaTools(IProcessRunner runner, IMediaToolResolver resolver, ILogger<MediaTools> logger, TimeProvider timeProvider, Func<string, MediaFileState> inspectFile)
    {
        ArgumentNullException.ThrowIfNull(runner);
        ArgumentNullException.ThrowIfNull(resolver);
        ArgumentNullException.ThrowIfNull(logger);
        ArgumentNullException.ThrowIfNull(timeProvider);
        ArgumentNullException.ThrowIfNull(inspectFile);
        _inspectFile = inspectFile;
        _runner = runner;
        _resolver = resolver;
        _logger = logger;
        _timeProvider = timeProvider;
    }

    /// <summary>
    /// <c>ffprobe_json</c>: probes <paramref name="path"/> and returns ffprobe's JSON object. Throws
    /// <see cref="MediaUnreadableException"/> when ffprobe says the contents are unreadable,
    /// <see cref="MediaToolException"/> for any other failure, and <see cref="MediaToolTimeoutException"/> on timeout.
    /// </summary>
    public async Task<JsonElement> FfprobeJsonAsync(
        string path,
        int timeoutSeconds = FfmpegCommands.FfprobeTimeoutSeconds,
        int probeSizeMb = 10,
        int analyzeDurationSeconds = 10,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(path);
        var (ffprobe, _) = _resolver.Resolve();
        var (resolvedPath, exists, isFile, size, mtime) = _inspectFile(path);
        LogFfprobeFileState(ProbeOutput.FileStateLogPayload(path, resolvedPath, exists, isFile, size, MediaPathNames.Suffix(path, _windows), mtime));
        if (!exists || !isFile || size == 0)
        {
            throw new MediaToolException("file missing or empty at probe time");
        }

        var argv = FfmpegCommands.BuildFfprobeArgv(ffprobe, path, probeSizeMb, analyzeDurationSeconds);
        LogFfprobeCall(ProbeOutput.CallLogPayload(path, argv));
        var result = await _runner.RunAsync(
            new ProcessRequest
            {
                Argv = argv,
                Timeout = TimeSpan.FromSeconds(timeoutSeconds),
                Stdin = ProcessInput.Inherit,
                Stdout = ProcessOutput.Capture,
                Stderr = ProcessOutput.Capture,
            },
            cancellationToken).ConfigureAwait(false);
        if (result.TimedOut)
        {
            throw new MediaToolTimeoutException(ProbeOutput.TimeoutMessage(argv, timeoutSeconds));
        }

        var stdout = ProbeOutput.CapturedText(result.Stdout);
        var stderr = ProbeOutput.CapturedText(result.Stderr);
        var payload = ProbeOutput.ResultLogPayload(path, result.ExitCode, stdout, stderr);
        if (result.ExitCode != 0)
        {
            LogFfprobeResultWarning(payload);
        }
        else
        {
            LogFfprobeResultDebug(payload);
        }

        return ProbeOutput.Interpret(result.ExitCode, stdout, stderr);
    }

    /// <summary><c>validate_remux_output</c>: probes the staged output and checks audio count and duration.</summary>
    public async Task ValidateRemuxOutputAsync(string path, int expectedAudio = 0, double? expectedDurationSeconds = null, CancellationToken cancellationToken = default)
    {
        var data = await FfprobeJsonAsync(path, cancellationToken: cancellationToken).ConfigureAwait(false);
        ProbeOutput.ValidateRemuxOutput(data, expectedAudio, expectedDurationSeconds);
    }

    /// <summary>
    /// <c>validate_media_integrity</c>: reads the primary video from start to finish and throws
    /// <see cref="MediaCompletenessException"/> for damaged or truncated input.
    /// </summary>
    /// <param name="path">The file to read.</param>
    /// <param name="expectedDurationSeconds">
    /// The probed duration, when known. Deliberate divergence (#539 item 3): the reference only looks at the
    /// exit code, so a Matroska file cut off mid-cluster keeps its header duration and a truncated demux that
    /// only warns (see <see cref="ProbeOutput.IntegrityIncompleteMarkers"/>) still reports success. When a
    /// duration is given, the last timestamp the demux actually reached (from <c>-progress pipe:1</c>) is
    /// compared against it with the same tolerance as <see cref="ProbeOutput.ValidateRemuxOutput"/>, "where
    /// practical" meaning: only when ffmpeg reported at least one timestamp, since a source with no video stream
    /// or one <c>-err_detect explode</c> kills before the first frame reports none.
    /// </param>
    /// <param name="cancellationToken">Cancellation.</param>
    /// <remarks>
    /// Deliberate divergence (#539 item 5): the reference skips this check entirely on Windows
    /// (<c>if os.name != "nt"</c> in <c>file_remux_pass/run.py</c>), reasoning that POSIX locks are advisory and a
    /// Docker bind-mount writer often does not take one, while Windows write handles are assumed exclusive. That
    /// assumption does not hold for every way Weir sees a file arrive on Windows — an SMB share, a WSL2 bind
    /// mount, or a downloader that preallocates then writes can all leave a reader able to open a file that is
    /// not finished. This method makes no such distinction and always does the full read; callers should not
    /// reintroduce a Windows skip without a concrete, current reason to.
    /// </remarks>
    public async Task ValidateMediaIntegrityAsync(string path, double? expectedDurationSeconds = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(path);
        var (_, ffmpeg) = _resolver.Resolve();
        var baseArgv = FfmpegCommands.BuildIntegrityArgv(ffmpeg, path);
        var wantsProgress = expectedDurationSeconds is > 0;
        var argv = wantsProgress ? FfmpegCommands.WithProgress(baseArgv) : baseArgv;
        var result = await _runner.RunAsync(
            new ProcessRequest
            {
                Argv = argv,
                Timeout = TimeSpan.FromSeconds(FfmpegCommands.FfmpegTimeoutSeconds),
                Stdin = ProcessInput.Null,
                Stdout = wantsProgress ? ProcessOutput.Capture : ProcessOutput.Discard,
                Stderr = ProcessOutput.Capture,
            },
            cancellationToken).ConfigureAwait(false);
        if (result.TimedOut)
        {
            throw new MediaToolTimeoutException(ProbeOutput.TimeoutMessage(argv, FfmpegCommands.FfmpegTimeoutSeconds));
        }

        var stderrText = ProbeOutput.CapturedText(result.Stderr);
        if (result.ExitCode != 0)
        {
            throw ProbeOutput.IntegrityFailure(stderrText);
        }

        if (ProbeOutput.HasIntegrityIncompleteMarker(stderrText))
        {
            throw ProbeOutput.IntegrityFailure(stderrText);
        }

        if (expectedDurationSeconds is { } expected && expected > 0
            && ProbeOutput.LastProgressOutTimeSeconds(ProbeOutput.CapturedText(result.Stdout)) is { } decoded)
        {
            var tolerance = Math.Max(5.0, expected * 0.01);
            if (decoded < expected - tolerance)
            {
                throw ProbeOutput.IntegrityShortfall(decoded, expected);
            }
        }
    }

    /// <summary>
    /// <c>run_ffmpeg</c>. Without a progress callback ffmpeg runs quietly; with one, <c>-progress pipe:1</c> is
    /// added and each block is reported. Failures throw <see cref="MediaToolException"/> carrying the tail of stderr.
    /// </summary>
    /// <remarks>
    /// Two #539 item 5 decisions, both deliberate divergences from the reference:
    /// <list type="bullet">
    /// <item>A plain (non-progress) timeout raises <see cref="MediaToolTimeoutException"/>, the same classified
    /// error probing uses, rather than letting <c>subprocess.TimeoutExpired</c> (an unrelated exception type in
    /// Python) escape uncaught. A progress-mode timeout still raises <see cref="MediaToolException"/> with
    /// "ffmpeg timed out" to match the reference's own message for that path.</item>
    /// <item>A timeout, in either mode, kills the whole process tree (<see cref="Processes.ProcessRunner"/>), not
    /// just the direct ffmpeg child the reference kills — ffmpeg can spawn helper processes (for some hwaccel or
    /// filter setups) that would otherwise survive and keep the output file open.</item>
    /// </list>
    /// The progress-mode timeout itself is enforced by <see cref="Processes.ProcessRunner"/> on a wall-clock timer
    /// independent of stdout activity (#539 item 4), unlike the reference's loop, which only checks its limit as a
    /// progress line arrives and so never stops a process that goes silent (stuck reading its input, for example).
    /// </remarks>
    public async Task RunFfmpegAsync(
        IReadOnlyList<string> argv,
        int? timeoutSeconds = FfmpegCommands.FfmpegTimeoutSeconds,
        Action<FfmpegProgressUpdate>? progressCallback = null,
        double? durationSeconds = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(argv);
        TimeSpan? timeout = timeoutSeconds is { } seconds ? TimeSpan.FromSeconds(seconds) : null;
        if (progressCallback is null)
        {
            var quiet = await _runner.RunAsync(
                new ProcessRequest
                {
                    Argv = argv,
                    Timeout = timeout,
                    Stdin = ProcessInput.Null,
                    Stdout = ProcessOutput.Discard,
                    Stderr = ProcessOutput.Tail,
                    TailBytes = FfmpegCommands.FfmpegStderrTailBytes,
                },
                cancellationToken).ConfigureAwait(false);
            if (quiet.TimedOut)
            {
                throw new MediaToolTimeoutException(ProbeOutput.TimeoutMessage(argv, timeoutSeconds ?? 0));
            }

            if (quiet.ExitCode != 0)
            {
                throw ProbeOutput.FfmpegFailure(ProbeOutput.TailText(quiet.Stderr));
            }

            return;
        }

        var progressArgv = FfmpegCommands.WithProgress(argv);
        var tracker = new FfmpegProgressTracker(durationSeconds, timeoutSeconds);
        var started = _timeProvider.GetTimestamp();
        var result = await _runner.RunAsync(
            new ProcessRequest
            {
                Argv = progressArgv,
                // The reference checks its limit only as lines arrive; the runner also enforces it for an ffmpeg
                // that goes silent, and kills the whole tree either way.
                Timeout = timeout,
                Stdin = ProcessInput.Null,
                Stderr = ProcessOutput.Tail,
                TailBytes = FfmpegCommands.FfmpegStderrTailBytes,
                ExitTimeoutAfterStdoutClosed = TimeSpan.FromSeconds(FfmpegCommands.ProgressExitWaitSeconds),
                OnStdoutLine = line =>
                {
                    var update = tracker.Feed(line, _timeProvider.GetElapsedTime(started).TotalSeconds);
                    if (update is not null)
                    {
                        progressCallback(update);
                    }
                },
            },
            cancellationToken).ConfigureAwait(false);
        switch (result.Timeout)
        {
            case ProcessTimeoutKind.Overall:
                throw new MediaToolException("ffmpeg timed out");
            case ProcessTimeoutKind.ExitAfterStdoutClosed:
                throw new MediaToolTimeoutException(ProbeOutput.TimeoutMessage(progressArgv, FfmpegCommands.ProgressExitWaitSeconds));
            case ProcessTimeoutKind.None:
            default:
                break;
        }

        if (result.ExitCode != 0)
        {
            throw ProbeOutput.FfmpegFailure(ProbeOutput.TailText(result.Stderr));
        }
    }

    /// <summary>
    /// <c>remux_to_temp_file</c>: writes the remux into <paramref name="workDir"/> and validates it. The temp file is
    /// deleted on any failure; the caller owns moving or deleting it on success.
    /// </summary>
    /// <param name="src">The source file to remux.</param>
    /// <param name="workDir">Where the temp output is written.</param>
    /// <param name="plan">Which streams to keep and how to tag them.</param>
    /// <param name="progressCallback">Reported to as ffmpeg runs, when given.</param>
    /// <param name="durationSeconds">The expected output duration, for progress percentage and output validation.</param>
    /// <param name="acceleration">
    /// The hardware acceleration decision, when one was made. Fixes #539 item 2: the reference builds an argv
    /// with the hwaccel flags only to show them (in <c>run.py</c>, for logging), and <c>remux_to_temp_file</c>
    /// builds its own argv that never includes <paramref name="acceleration"/>'s flags, so the setting has no
    /// effect on what actually runs. Here <see cref="FfmpegCommands.BuildRemuxArgv"/> is the one builder used for
    /// both: its result is what <see cref="LogFfmpegDebug"/> shows and what <see cref="RunFfmpegAsync"/> executes,
    /// so a decided acceleration can no longer diverge between the two.
    /// </param>
    /// <param name="cancellationToken">Cancellation.</param>
    public async Task<string> RemuxToTempFileAsync(
        string src,
        string workDir,
        RemuxPlan plan,
        Action<FfmpegProgressUpdate>? progressCallback = null,
        double? durationSeconds = null,
        AccelerationDecision? acceleration = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(src);
        ArgumentNullException.ThrowIfNull(workDir);
        ArgumentNullException.ThrowIfNull(plan);
        var (_, ffmpeg) = _resolver.Resolve();
        Directory.CreateDirectory(workDir);
        var suffix = MediaPathNames.Suffix(src, _windows);
        var tmpPath = CreateTempFile(workDir, prefix: MediaPathNames.Stem(src, _windows) + ".refiner.", suffix: suffix.Length > 0 ? suffix : ".mkv");
        try
        {
            var argv = FfmpegCommands.BuildRemuxArgv(ffmpeg, src, tmpPath, plan, acceleration?.ArgvFlags);
            LogFfmpegDebug(FfmpegCommands.DebugSummary(argv));
            await RunFfmpegAsync(argv, progressCallback: progressCallback, durationSeconds: durationSeconds, cancellationToken: cancellationToken).ConfigureAwait(false);
            await ValidateRemuxOutputAsync(tmpPath, plan.Audio.Count, durationSeconds, cancellationToken).ConfigureAwait(false);
        }
        catch
        {
            try
            {
                if (File.Exists(tmpPath))
                {
                    File.Delete(tmpPath);
                }
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                LogTempRemoveFailed(error, tmpPath);
            }

            throw;
        }

        return tmpPath;
    }

    /// <summary>
    /// <c>detect_acceleration</c>: what ffmpeg was built with. Never throws for a missing, failing or slow ffmpeg;
    /// the report says why nothing was found.
    /// </summary>
    /// <remarks>
    /// #539 item 5: the reference decodes <c>ffmpeg -hwaccels</c>'s output with the process's locale encoding
    /// (subprocess's default), which can raise or mangle text on a locale that is not UTF-8. This always decodes
    /// as UTF-8 with replacement (<see cref="ProbeOutput.CapturedText"/>), matching every other tool output this
    /// class reads; the method names it detects (<c>cuda</c>, <c>qsv</c>, …) are ASCII, so the only practical
    /// effect is that a mangled heading line is filtered out instead of raising.
    /// </remarks>
    public async Task<AccelerationReport> DetectAccelerationAsync(string ffmpegBin, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(ffmpegBin);
        var argv = FfmpegCommands.BuildHwaccelsArgv(ffmpegBin);
        ProcessResult result;
        try
        {
            result = await _runner.RunAsync(
                new ProcessRequest
                {
                    Argv = argv,
                    Timeout = TimeSpan.FromSeconds(FfmpegCommands.HwaccelTimeoutSeconds),
                    Stdin = ProcessInput.Inherit,
                    Stdout = ProcessOutput.Capture,
                    Stderr = ProcessOutput.Capture,
                },
                cancellationToken).ConfigureAwait(false);
        }
        catch (Exception error) when (error is Win32Exception or IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            return HardwareAcceleration.ReportForRunError(error.Message);
        }

        if (result.TimedOut)
        {
            return HardwareAcceleration.ReportForRunError(ProbeOutput.TimeoutMessage(argv, FfmpegCommands.HwaccelTimeoutSeconds));
        }

        return HardwareAcceleration.ReportFromHwaccels(result.ExitCode, ProbeOutput.CapturedText(result.Stdout));
    }

    /// <summary><c>tempfile.mkstemp</c>: a new file named prefix + 8 random characters + suffix, created exclusively.</summary>
    private static string CreateTempFile(string directory, string prefix, string suffix)
    {
        const string Characters = "abcdefghijklmnopqrstuvwxyz0123456789_";
        for (var attempt = 0; ; attempt++)
        {
            var name = prefix + RandomNumberGenerator.GetString(Characters, 8) + suffix;
            var path = Path.GetFullPath(Path.Combine(directory, name));
            try
            {
                using (new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None))
                {
                }

                return path;
            }
            catch (IOException) when (attempt < 100 && File.Exists(path))
            {
                // Name taken; draw again.
            }
        }
    }

    /// <summary>What <c>ffprobe_json</c> reads about the file before probing it.</summary>
    internal static MediaFileState InspectFile(string path)
    {
        var resolvedPath = ResolvePath(path);
        var exists = File.Exists(path) || Directory.Exists(path);
        var isFile = File.Exists(path);
        long size;
        double mtime;
        try
        {
            if (isFile)
            {
                var info = new FileInfo(path);
                size = info.Length;
                mtime = (info.LastWriteTimeUtc - DateTime.UnixEpoch).TotalSeconds;
            }
            else if (exists)
            {
                size = 0;
                mtime = (Directory.GetLastWriteTimeUtc(path) - DateTime.UnixEpoch).TotalSeconds;
            }
            else
            {
                size = -1;
                mtime = 0.0;
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            size = -1;
            mtime = 0.0;
        }


        return new MediaFileState(resolvedPath, exists, isFile, size, mtime);
    }

    private static string ResolvePath(string path)
    {
        try
        {
            return Path.GetFullPath(path);
        }
        catch (Exception error) when (error is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return path;
        }
    }

    [LoggerMessage(Level = LogLevel.Debug, Message = "REFINER_FFPROBE_FILE_STATE: {Payload}")]
    private partial void LogFfprobeFileState(string payload);

    [LoggerMessage(Level = LogLevel.Debug, Message = "REFINER_FFPROBE_CALL: {Payload}")]
    private partial void LogFfprobeCall(string payload);

    [LoggerMessage(Level = LogLevel.Debug, Message = "REFINER_FFPROBE_RESULT: {Payload}")]
    private partial void LogFfprobeResultDebug(string payload);

    [LoggerMessage(Level = LogLevel.Warning, Message = "REFINER_FFPROBE_RESULT: {Payload}")]
    private partial void LogFfprobeResultWarning(string payload);

    [LoggerMessage(Level = LogLevel.Debug, Message = "{Summary}")]
    private partial void LogFfmpegDebug(string summary);

    [LoggerMessage(Level = LogLevel.Warning, Message = "Refiner: could not remove temp file {Path}")]
    private partial void LogTempRemoveFailed(Exception error, string path);
}

/// <summary>The file facts <c>ffprobe_json</c> logs and checks: resolved path, existence, size and mtime (seconds since the epoch).</summary>
internal readonly record struct MediaFileState(string ResolvedPath, bool Exists, bool IsFile, long SizeBytes, double MtimeEpoch);
