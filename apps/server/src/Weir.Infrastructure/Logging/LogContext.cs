namespace Weir.Infrastructure.Logging;

/// <summary>
/// Per-request and per-job identifiers that every log line carries as <c>correlation_id</c> and
/// <c>job_id</c> (port of <c>weir.platform.http.request_context</c>).
/// </summary>
public static class LogContext
{
    private static readonly AsyncLocal<string?> CurrentRequestId = new();
    private static readonly AsyncLocal<string?> CurrentJobId = new();

    public static string? RequestId => CurrentRequestId.Value;

    public static string? JobId => CurrentJobId.Value;

    /// <summary>Set the request id for the rest of this async flow; dispose to restore the previous value.</summary>
    public static IDisposable BeginRequest(string requestId)
    {
        var previousRequest = CurrentRequestId.Value;
        var previousJob = CurrentJobId.Value;
        CurrentRequestId.Value = requestId;
        CurrentJobId.Value = null;
        return new Restore(() =>
        {
            CurrentRequestId.Value = previousRequest;
            CurrentJobId.Value = previousJob;
        });
    }

    /// <summary>Set the job id for the rest of this async flow; dispose to restore the previous value.</summary>
    public static IDisposable BeginJob(string? jobId)
    {
        var previous = CurrentJobId.Value;
        CurrentJobId.Value = jobId;
        return new Restore(() => CurrentJobId.Value = previous);
    }

    private sealed class Restore(Action restore) : IDisposable
    {
        private Action? _restore = restore;

        public void Dispose()
        {
            Interlocked.Exchange(ref _restore, null)?.Invoke();
        }
    }
}
