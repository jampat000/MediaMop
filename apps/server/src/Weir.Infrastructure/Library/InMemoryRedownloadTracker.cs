using System.Collections.Concurrent;
using Weir.Core.Library;

namespace Weir.Infrastructure.Library;

/// <summary>
/// The default <see cref="IRedownloadTracker"/> (#509 step 4): in-memory, for the same reason
/// <see cref="InMemoryRemovedTrackStore"/> is — nothing yet calls <see cref="ClearAsync"/> from a real
/// download pipeline (that hook belongs to library mode, #505, or the watched-folder intake once either is
/// wired to call it), so there is nothing durable a restart could lose today. Safe as a DI singleton.
/// </summary>
public sealed class InMemoryRedownloadTracker : IRedownloadTracker
{
    private readonly ConcurrentDictionary<RemovedTrackFileKey, WaitingForRedownload> _waiting = new();
    private readonly TimeProvider _time;

    public InMemoryRedownloadTracker(TimeProvider? time = null)
    {
        _time = time ?? TimeProvider.System;
    }

    public Task MarkWaitingAsync(RemovedTrackFileKey file, string reason, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(file);
        ArgumentNullException.ThrowIfNull(reason);
        _waiting[file] = new WaitingForRedownload(file, reason, _time.GetUtcNow());
        return Task.CompletedTask;
    }

    public Task<bool> ClearAsync(RemovedTrackFileKey file, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(file);
        return Task.FromResult(_waiting.TryRemove(file, out _));
    }

    public Task<bool> IsWaitingAsync(RemovedTrackFileKey file, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(file);
        return Task.FromResult(_waiting.ContainsKey(file));
    }

    public Task<IReadOnlyList<WaitingForRedownload>> ListWaitingAsync(CancellationToken cancellationToken = default) =>
        Task.FromResult<IReadOnlyList<WaitingForRedownload>>([.. _waiting.Values.OrderBy(item => item.RequestedAt)]);
}
