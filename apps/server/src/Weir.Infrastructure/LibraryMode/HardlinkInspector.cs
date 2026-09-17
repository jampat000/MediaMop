namespace Weir.Infrastructure.LibraryMode;

/// <summary>The filesystem read <see cref="Weir.Core.LibraryMode.HardlinkPolicy"/> needs: how many names point at a file's data.</summary>
public interface IHardlinkInspector
{
    /// <summary>Hard links to <paramref name="path"/>, or <see langword="null"/> when the platform cannot say.</summary>
    int? LinkCount(string path);
}

/// <summary>
/// The real filesystem's link count (issue #508 step 1), delegating to <see cref="PhysicalSwapFileSystem.LinkCount"/>
/// rather than repeating its own copy of the same <c>GetFileInformationByHandle</c>/<c>statx</c> P/Invoke declarations.
/// </summary>
/// <remarks>
/// Issue #506 (crash-safe in-place swap) reads the same two OS facts through <c>ISwapFileSystem.LinkCount</c>
/// (<c>Weir.Infrastructure/LibraryMode/SwapFileSystem.cs</c>, <c>PhysicalSwapFileSystem</c>) for the same reason:
/// the swap itself must not silently double disk use on a still-shared file either. #508 originally carried its
/// own copy of the native declarations, written before #506 had landed here; now that both are on the same
/// branch, this type keeps only the smaller, preflight-only seam (<see cref="IHardlinkInspector"/>) and forwards
/// to the one real implementation instead of maintaining a second native binding that could drift from it.
/// </remarks>
public sealed class PhysicalHardlinkInspector : IHardlinkInspector
{
    public static PhysicalHardlinkInspector Instance { get; } = new();

    public int? LinkCount(string path)
    {
        ArgumentNullException.ThrowIfNull(path);
        return PhysicalSwapFileSystem.Instance.LinkCount(path);
    }
}
