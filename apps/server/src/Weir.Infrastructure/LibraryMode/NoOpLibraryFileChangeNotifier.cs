using Microsoft.Extensions.Logging;
using Weir.Core.MediaManagers;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>
/// The #507 seam's default until <c>feat/507-file-changed</c> (Sonarr/Radarr rescan, Deluno's file-changed capability,
/// retry-with-backoff, per-title de-duplication) merges here: it makes no call and only logs, so a library-mode clean never
/// fails or blocks on the manager notify step. Once #507 lands, its own <c>LibraryFileChangeNotifier</c> registration
/// replaces this one (see <c>Weir.Infrastructure.LibraryMode.LibraryModeServices.AddWeirLibraryMode</c>).
/// </summary>
public sealed class NoOpLibraryFileChangeNotifier : ILibraryFileChangeNotifier
{
    private readonly ILogger<NoOpLibraryFileChangeNotifier> _logger;

    public NoOpLibraryFileChangeNotifier(ILogger<NoOpLibraryFileChangeNotifier> logger)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public Task NotifyAsync(LibraryFileChange change, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(change);
        _logger.LogInformation(
            "Library mode cleaned {Path}, but #507 (telling the media manager) is not wired in on this build; it will catch up at its next disk scan.",
            change.FilePath);
        return Task.CompletedTask;
    }
}
