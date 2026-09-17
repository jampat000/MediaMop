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
    public async Task ValidateMediaIntegrityAsync(string path, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(path);
        var (_, ffmpeg) = _resolver.Resolve();
        var argv = FfmpegCommands.BuildIntegrityArgv(ffmpeg, path);
        var result = await _runner.RunAsync(
            new ProcessRequest
            {
                Argv = argv,
                Timeout = TimeSpan.FromSeconds(FfmpegCommands.FfmpegTimeoutSeconds),
                Stdin = ProcessInput.Null,
                Stdout = ProcessOutput.Discard,
                Stderr = ProcessOutput.Capture,
            },
            cancellationToken).ConfigureAwait(false);
        if (result.TimedOut)
        {
            throw new MediaToolTimeoutException(ProbeOutput.TimeoutMessage(argv, FfmpegCommands.FfmpegTimeoutSeconds));
        }

        if (result.ExitCode != 0)
        {
            throw ProbeOutput.IntegrityFailure(ProbeOutput.CapturedText(result.Stderr));
        }
    }

    /// <summary>
    /// <c>run_ffmpeg</c>. Without a progress callback ffmpeg runs quietly; with one, <c>-progress pipe:1</c> is
    /// added and each block is reported. Failures throw <see cref="MediaToolException"/> carrying the tail of stderr.
    /// </summary>
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
    public async Task<string> RemuxToTempFileAsync(
        string src,
        string workDir,
        RemuxPlan plan,
        Action<FfmpegProgressUpdate>? progressCallback = null,
        double? durationSeconds = null,
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
            var argv = FfmpegCommands.BuildRemuxArgv(ffmpeg, src, tmpPath, plan);
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
