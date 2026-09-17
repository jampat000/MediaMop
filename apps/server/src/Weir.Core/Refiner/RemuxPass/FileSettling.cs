using System.Globalization;

namespace Weir.Core.Refiner.RemuxPass;

/// <summary>What one scan saw, and what the next one needs to remember (<c>SettlingObservation</c>).</summary>
public sealed record SettlingObservation(bool IsSettling, DateTimeOffset? SizeChangedAt, DateTimeOffset? StableAt, string? Reason = null);

/// <summary>
/// Has a file finished being written? The pure half of <c>refiner_file_settling.py</c>: two observations of the same size, far
/// enough apart, are evidence that writing stopped. The read guard and access checks live in
/// <c>Weir.Infrastructure.Refiner.RemuxPass.SourceReadGuard</c>.
/// </summary>
public static class FileSettling
{
    /// <summary>
    /// <c>observe_size_settling</c>: compare this scan's size against the last one. A file seen for the first time is still
    /// settling, because one observation cannot show that anything has stopped.
    /// </summary>
    /// <param name="library">The library's detection settings.</param>
    /// <param name="previousSizeBytes">The size the previous scan recorded, or null when there is no previous row.</param>
    /// <param name="previousSizeChangedAt">When the previous row's size last changed, when recorded.</param>
    /// <param name="currentSizeBytes">This scan's size.</param>
    /// <param name="now">Now.</param>
    public static SettlingObservation ObserveSizeSettling(
        RefinerLibraryRecord library,
        long? previousSizeBytes,
        DateTimeOffset? previousSizeChangedAt,
        long currentSizeBytes,
        DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(library);
        var interval = Math.Max(0, library.FileDetectionIntervalSeconds);
        if (library.IgnoreSizeChanges || interval == 0)
        {
            return new SettlingObservation(false, now, now);
        }

        var stableFromNow = now + TimeSpan.FromSeconds(interval);
        if (previousSizeBytes is null)
        {
            return new SettlingObservation(
                true, now, stableFromNow,
                "Weir has only just found this file and is checking whether anything is still writing to it.");
        }

        if (previousSizeBytes.Value != currentSizeBytes)
        {
            return new SettlingObservation(
                true, now, stableFromNow,
                "This file is still growing, so something is writing to it. Weir will wait until it stops.");
        }

        if (previousSizeChangedAt is not { } changedAt)
        {
            return new SettlingObservation(true, now, stableFromNow, "Weir is confirming that nothing is still writing to this file.");
        }

        var stableAt = changedAt + TimeSpan.FromSeconds(interval);
        if (now < stableAt)
        {
            return new SettlingObservation(
                true, changedAt, stableAt,
                $"This file stopped changing very recently. Weir waits {interval.ToString(CultureInfo.InvariantCulture)}s to be sure nothing " +
                "else is writing to it.");
        }

        return new SettlingObservation(false, changedAt, stableAt);
    }
}
