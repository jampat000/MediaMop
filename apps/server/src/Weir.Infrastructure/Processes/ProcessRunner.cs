using System.Buffers;
using System.ComponentModel;
using System.Diagnostics;
using Weir.Core.Media;

namespace Weir.Infrastructure.Processes;

/// <summary>What a child process reads on stdin.</summary>
public enum ProcessInput
{
    /// <summary>End of file immediately (<c>subprocess.DEVNULL</c>).</summary>
    Null,

    /// <summary>This process's own stdin (the <c>subprocess</c> default).</summary>
    Inherit,
}

/// <summary>What happens to a child's stdout or stderr.</summary>
public enum ProcessOutput
{
    /// <summary>Read and dropped, so the child never blocks on a full pipe.</summary>
    Discard,

    /// <summary>Kept in full.</summary>
    Capture,

    /// <summary>Only the last <see cref="ProcessRequest.TailBytes"/> bytes are kept.</summary>
    Tail,
}

/// <summary>How a run ended when it did not end by itself.</summary>
public enum ProcessTimeoutKind
{
    None,

    /// <summary><see cref="ProcessRequest.Timeout"/> elapsed.</summary>
    Overall,

    /// <summary>stdout closed but the process did not exit within <see cref="ProcessRequest.ExitTimeoutAfterStdoutClosed"/>.</summary>
    ExitAfterStdoutClosed,
}

/// <summary>One child process to run, argv token for token (no shell).</summary>
public sealed record ProcessRequest
{
    /// <summary>The executable, then its arguments.</summary>
    public required IReadOnlyList<string> Argv { get; init; }

    /// <summary>Wall-clock limit; the whole process tree is killed when it passes.</summary>
    public TimeSpan? Timeout { get; init; }

    public ProcessInput Stdin { get; init; } = ProcessInput.Null;

    public ProcessOutput Stdout { get; init; } = ProcessOutput.Capture;

    public ProcessOutput Stderr { get; init; } = ProcessOutput.Capture;

    public int TailBytes { get; init; } = 32 * 1024;

    /// <summary>
    /// Called for each stdout line as it arrives, decoded as UTF-8 with replacement and split with universal
    /// newlines (<c>\n</c>, <c>\r\n</c>, <c>\r</c>), without the line end. If it throws, the process tree is
    /// killed and the exception is rethrown from <see cref="IProcessRunner.RunAsync"/>. Stdout is not captured
    /// when this is set.
    /// </summary>
    public Action<string>? OnStdoutLine { get; init; }

    /// <summary>With <see cref="OnStdoutLine"/>: how long to wait for exit once stdout closes.</summary>
    public TimeSpan? ExitTimeoutAfterStdoutClosed { get; init; }

    public string? WorkingDirectory { get; init; }
}

/// <summary>How a child process ended and what it wrote.</summary>
public sealed record ProcessResult
{
    /// <summary>The exit code; meaningless (the kill's code) when <see cref="TimedOut"/>.</summary>
    public required int ExitCode { get; init; }

    public byte[] Stdout { get; init; } = [];

    public byte[] Stderr { get; init; } = [];

    public ProcessTimeoutKind Timeout { get; init; }

    public bool TimedOut => Timeout != ProcessTimeoutKind.None;
}

/// <summary>Runs external tools. Behind an interface so callers can be tested without them.</summary>
public interface IProcessRunner
{
    /// <summary>
    /// Runs <paramref name="request"/> to completion. Cancellation and timeouts kill the whole process tree.
    /// A cancelled run throws <see cref="OperationCanceledException"/>; a timed-out run returns with
    /// <see cref="ProcessResult.Timeout"/> set. A missing executable throws <see cref="Win32Exception"/>.
    /// </summary>
    Task<ProcessResult> RunAsync(ProcessRequest request, CancellationToken cancellationToken = default);
}

/// <summary><see cref="IProcessRunner"/> over <see cref="Process"/>, for Windows and Linux.</summary>
public sealed class ProcessRunner : IProcessRunner
{
    /// <summary>How long to wait for pipes to drain after a kill before giving up on them.</summary>
    private static readonly TimeSpan DrainAfterKill = TimeSpan.FromSeconds(5);

    public async Task<ProcessResult> RunAsync(ProcessRequest request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (request.Argv.Count == 0)
        {
            throw new ArgumentException("A process needs an executable.", nameof(request));
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = request.Argv[0],
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = request.Stdin == ProcessInput.Null,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in request.Argv.Skip(1))
        {
            startInfo.ArgumentList.Add(argument);
        }

        if (request.WorkingDirectory is not null)
        {
            startInfo.WorkingDirectory = request.WorkingDirectory;
        }

        using var process = new Process { StartInfo = startInfo };
        process.Start();
        if (request.Stdin == ProcessInput.Null)
        {
            process.StandardInput.Close();
        }

        using var timeoutSource = request.Timeout is { } timeout ? new CancellationTokenSource(timeout) : new CancellationTokenSource();
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutSource.Token);

        Exception? callbackError = null;
        var stdoutSink = new OutputSink(request.OnStdoutLine is null ? request.Stdout : ProcessOutput.Discard, request.TailBytes);
        var stderrSink = new OutputSink(request.Stderr, request.TailBytes);
        UniversalNewlineSplitter? lines = request.OnStdoutLine is null
            ? null
            : new UniversalNewlineSplitter(line =>
            {
                if (callbackError is not null)
                {
                    return;
                }

                try
                {
                    request.OnStdoutLine(line);
                }
#pragma warning disable CA1031 // The callback's exception is rethrown to the caller after the kill.
                catch (Exception error)
#pragma warning restore CA1031
                {
                    callbackError = error;
                    KillTree(process);
                }
            });

        var stdoutTask = PumpAsync(process.StandardOutput.BaseStream, stdoutSink, lines);
        var stderrTask = PumpAsync(process.StandardError.BaseStream, stderrSink, null);
        var timedOut = ProcessTimeoutKind.None;

        try
        {
            if (lines is not null)
            {
                await stdoutTask.WaitAsync(linked.Token).ConfigureAwait(false);
                if (callbackError is null && request.ExitTimeoutAfterStdoutClosed is { } grace)
                {
                    using var graceSource = CancellationTokenSource.CreateLinkedTokenSource(linked.Token);
                    graceSource.CancelAfter(grace);
                    try
                    {
                        await process.WaitForExitAsync(graceSource.Token).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException) when (!linked.IsCancellationRequested)
                    {
                        timedOut = ProcessTimeoutKind.ExitAfterStdoutClosed;
                        KillTree(process);
                    }
                }
            }

            await process.WaitForExitAsync(linked.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (linked.IsCancellationRequested)
        {
            KillTree(process);
            await DrainAsync(process, stdoutTask, stderrTask).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            timedOut = ProcessTimeoutKind.Overall;
        }

        await DrainAsync(process, stdoutTask, stderrTask).ConfigureAwait(false);
        if (callbackError is not null)
        {
            System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(callbackError).Throw();
        }

        return new ProcessResult
        {
            ExitCode = process.HasExited ? process.ExitCode : -1,
            Stdout = stdoutSink.ToArray(),
            Stderr = stderrSink.ToArray(),
            Timeout = timedOut,
        };
    }

    private static async Task DrainAsync(Process process, Task stdoutTask, Task stderrTask)
    {
        try
        {
            await Task.WhenAll(stdoutTask, stderrTask).WaitAsync(DrainAfterKill).ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            // A grandchild outside the tree kept a pipe open; what was read is what there is.
        }

        using var exit = new CancellationTokenSource(DrainAfterKill);
        try
        {
            await process.WaitForExitAsync(exit.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // Reported through HasExited.
        }
    }

    private static void KillTree(Process process)
    {
        try
        {
            process.Kill(entireProcessTree: true);
        }
        catch (InvalidOperationException)
        {
            // Already exited.
        }
        catch (Win32Exception)
        {
            // Exiting while being killed, or access denied to a descendant: nothing more to do.
        }
        catch (AggregateException)
        {
            // Some descendants could not be killed; the process itself was.
        }
    }

    private static async Task PumpAsync(Stream stream, OutputSink sink, UniversalNewlineSplitter? lines)
    {
        var buffer = new byte[16 * 1024];
        while (true)
        {
            int read;
            try
            {
                read = await stream.ReadAsync(buffer).ConfigureAwait(false);
            }
            catch (IOException)
            {
                break;
            }
            catch (ObjectDisposedException)
            {
                break;
            }

            if (read == 0)
            {
                break;
            }

            sink.Write(buffer.AsSpan(0, read));
            lines?.Feed(buffer.AsSpan(0, read));
        }

        lines?.Finish();
    }

    /// <summary>Keeps everything, the tail, or nothing.</summary>
    private sealed class OutputSink(ProcessOutput mode, int tailBytes)
    {
        private ArrayBufferWriter<byte> _buffer = new();

        public void Write(ReadOnlySpan<byte> data)
        {
            switch (mode)
            {
                case ProcessOutput.Capture:
                    _buffer.Write(data);
                    break;
                case ProcessOutput.Tail:
                    _buffer.Write(data);
                    if (_buffer.WrittenCount > tailBytes * 2L)
                    {
                        var kept = _buffer.WrittenSpan[^tailBytes..].ToArray();
                        _buffer = new ArrayBufferWriter<byte>(tailBytes * 2);
                        _buffer.Write(kept);
                    }

                    break;
                case ProcessOutput.Discard:
                default:
                    break;
            }
        }

        public byte[] ToArray()
        {
            var all = _buffer.WrittenSpan;
            return (mode == ProcessOutput.Tail && all.Length > tailBytes ? all[^tailBytes..] : all).ToArray();
        }
    }
}
