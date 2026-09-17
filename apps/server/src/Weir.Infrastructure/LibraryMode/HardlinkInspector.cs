using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>The filesystem read <see cref="Weir.Core.LibraryMode.HardlinkPolicy"/> needs: how many names point at a file's data.</summary>
public interface IHardlinkInspector
{
    /// <summary>Hard links to <paramref name="path"/>, or <see langword="null"/> when the platform cannot say.</summary>
    int? LinkCount(string path);
}

/// <summary>
/// The real filesystem's link count (issue #508 step 1). <c>GetFileInformationByHandle</c>'s <c>nNumberOfLinks</c>
/// on Windows (a handle opened for attributes only, so it works on a file a download client still holds open for
/// seeding); <c>statx</c>'s <c>stx_nlink</c> on Linux. Other platforms report unknown.
/// </summary>
/// <remarks>
/// Issue #506 (crash-safe in-place swap, a separate branch not yet on <c>main</c> as this was written) reads the
/// same two OS facts through its own <c>ISwapFileSystem.LinkCount</c>
/// (<c>Weir.Infrastructure/LibraryMode/SwapFileSystem.cs</c>, <c>PhysicalSwapFileSystem</c>), for the same reason:
/// the swap itself must not silently double disk use on a still-shared file either. Once both land on <c>main</c>,
/// one of the two should be removed in favour of the other rather than keeping both — this type is the smaller,
/// preflight-only half (no swap-file concerns), so it is a plausible candidate to drop.
/// </remarks>
public sealed partial class PhysicalHardlinkInspector : IHardlinkInspector
{
    private const uint FileReadAttributes = 0x80;
    private const uint FileShareAll = 0x1 | 0x2 | 0x4;
    private const uint OpenExisting = 3;
    private const uint FileFlagBackupSemantics = 0x02000000;

    public static PhysicalHardlinkInspector Instance { get; } = new();

    public int? LinkCount(string path)
    {
        ArgumentNullException.ThrowIfNull(path);
        if (OperatingSystem.IsWindows())
        {
            return WindowsLinkCount(path);
        }

        return OperatingSystem.IsLinux() ? LinuxLinkCount(path) : null;
    }

    private static int WindowsLinkCount(string path)
    {
        using var handle = OpenWindowsHandle(path);
        if (handle.IsInvalid)
        {
            var error = Marshal.GetLastWin32Error();
            if (error is 2 or 3) // ERROR_FILE_NOT_FOUND / ERROR_PATH_NOT_FOUND
            {
                throw new FileNotFoundException($"No such file: '{path}'", path);
            }

            throw new IOException($"Could not open '{path}' ({new Win32Exception(error).Message})");
        }

        return GetFileInformationByHandle(handle, out var information)
            ? (int)information.NumberOfLinks
            : throw new IOException($"Could not read link count for '{path}' ({new Win32Exception(Marshal.GetLastWin32Error()).Message})");
    }

    private static SafeFileHandle OpenWindowsHandle(string path) =>
        CreateFileW(path, FileReadAttributes, FileShareAll, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics, IntPtr.Zero);

    [LibraryImport("kernel32.dll", EntryPoint = "CreateFileW", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    private static partial SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr securityAttributes, uint disposition, uint flags, IntPtr template);

    [LibraryImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetFileInformationByHandle(SafeFileHandle file, out ByHandleFileInformation information);

    // BY_HANDLE_FILE_INFORMATION packs every field on a 4-byte boundary natively (each FILETIME is two DWORDs, not
    // an 8-byte-aligned value) — without Pack = 4 the CLR would 8-byte-align the two long fields below and insert
    // padding the native struct does not have, silently shifting NumberOfLinks (and everything after it) to the
    // wrong offset.
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct ByHandleFileInformation
    {
        public uint FileAttributes;
        public long CreationTime;
        public long LastAccessTime;
        public long LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }

    private static int? LinuxLinkCount(string path)
    {
        // struct statx: stx_mask (u32) at offset 0, stx_nlink (u32) at offset 16 (Linux is the same layout on
        // every architecture this runs on). Mirrors Weir.Infrastructure/LibraryMode/SwapFileSystem.cs's own
        // Statx use (issue #506) rather than adding a second native declaration with a different shape.
        const uint statxNlink = 0x4;
        const int atFdCwd = -100;
        Span<byte> buffer = stackalloc byte[256];
        if (Statx(atFdCwd, path, 0, statxNlink, ref buffer[0]) != 0)
        {
            var errno = Marshal.GetLastPInvokeError();
            if (errno == 2)
            {
                throw new FileNotFoundException($"No such file: '{path}'", path);
            }

            throw new IOException($"statx failed with errno {errno} for '{path}'");
        }

        var mask = BitConverter.ToUInt32(buffer[..4]);
        if ((mask & statxNlink) == 0)
        {
            return null;
        }

        return (int)BitConverter.ToUInt32(buffer.Slice(16, 4));
    }

    [LibraryImport("libc", EntryPoint = "statx", SetLastError = true, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int Statx(int dirFd, string path, int flags, uint mask, ref byte statxBuffer);
}
