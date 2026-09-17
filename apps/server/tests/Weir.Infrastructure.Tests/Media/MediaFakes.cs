using Microsoft.Extensions.Logging;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Processes;

namespace Weir.Infrastructure.Tests.Media;

/// <summary>A runner that answers from a script instead of starting processes.</summary>
internal sealed class ScriptedRunner(Func<ProcessRequest, ScriptedRun> script) : IProcessRunner
{
    public List<ProcessRequest> Requests { get; } = [];

    public bool Killed { get; private set; }

    public Task<ProcessResult> RunAsync(ProcessRequest request, CancellationToken cancellationToken = default)
    {
        Requests.Add(request);
        var run = script(request);
        if (run.Throw is not null)
        {
            throw run.Throw;
        }

        if (request.OnStdoutLine is not null)
        {
            foreach (var line in run.Lines)
            {
                try
                {
                    request.OnStdoutLine(line);
                }
                catch
                {
                    // What ProcessRunner does: kill the tree, then rethrow.
                    Killed = true;
                    throw;
                }
            }
        }

        return Task.FromResult(new ProcessResult
        {
            ExitCode = run.ExitCode,
            Stdout = run.Stdout,
            Stderr = run.Stderr,
            Timeout = run.Timeout,
        });
    }
}

internal sealed record ScriptedRun
{
    public int ExitCode { get; init; }

    public byte[] Stdout { get; init; } = [];

    public byte[] Stderr { get; init; } = [];

    public IReadOnlyList<string> Lines { get; init; } = [];

    public ProcessTimeoutKind Timeout { get; init; }

    public Exception? Throw { get; init; }
}

internal sealed class FixedResolver(string ffprobe = "ffprobe", string ffmpeg = "ffmpeg", string? mkvmerge = null) : IMediaToolResolver
{
    public (string Ffprobe, string Ffmpeg) Resolve() => (ffprobe, ffmpeg);

    public string? ResolveMkvmerge() => mkvmerge;
}

/// <summary>Hands out the given clock readings (seconds) in order, repeating the last.</summary>
internal sealed class ScriptedTimeProvider(IReadOnlyList<double> seconds) : TimeProvider
{
    private int _next;

    public override long TimestampFrequency => TimeSpan.TicksPerSecond;

    public override long GetTimestamp()
    {
        var value = seconds.Count == 0 ? 0 : seconds[Math.Min(_next, seconds.Count - 1)];
        _next++;
        return (long)Math.Round(value * TimeSpan.TicksPerSecond);
    }
}

internal sealed class ListLogger<T> : ILogger<T>
{
    public List<(LogLevel Level, string Message)> Entries { get; } = [];

    public IDisposable? BeginScope<TState>(TState state)
        where TState : notnull => null;

    public bool IsEnabled(LogLevel logLevel) => true;

    public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter) =>
        Entries.Add((logLevel, formatter(state, exception)));
}
