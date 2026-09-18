using Weir.Core.MediaManagers;

namespace Weir.Infrastructure.Processing.RemuxPass;

/// <summary>
/// <c>_pace</c>: minimum spacing between outbound rejects, across the whole process (registered as a singleton so its
/// state is shared the way the reference's module-level lock and clock are). Uses an asynchronous wait rather than
/// Python's blocking <c>time.sleep</c>, so it never ties up a worker thread while it waits.
/// </summary>
public sealed class RejectPacing : IDisposable
{
    private readonly TimeProvider _time;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private DateTimeOffset _lastRejectAt = DateTimeOffset.MinValue;

    public RejectPacing(TimeProvider time)
    {
        _time = time ?? throw new ArgumentNullException(nameof(time));
    }

    public async Task WaitAsync(CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var wait = RejectSupportRules.MinSecondsBetweenRejects - (_time.GetUtcNow() - _lastRejectAt);
            if (wait > TimeSpan.Zero)
            {
                await Task.Delay(wait, _time, cancellationToken).ConfigureAwait(false);
            }

            _lastRejectAt = _time.GetUtcNow();
        }
        finally
        {
            _gate.Release();
        }
    }

    public void Dispose() => _gate.Dispose();
}
