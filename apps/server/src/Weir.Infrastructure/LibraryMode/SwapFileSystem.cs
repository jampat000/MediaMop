using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using Microsoft.Win32.SafeHandles;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Infrastructure.LibraryMode;

/// <summary>Another program holds the file: a Windows sharing or lock violation, or <c>EBUSY</c>/<c>ETXTBSY</c> elsewhere.</summary>
public sealed class FileInUseException : IOException
{
    public FileInUseException()
    {
    }

    public FileInUseException(string message)
        : base(message)
    {
    }

    public FileInUseException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// Every filesystem operation the swap and its sweep perform, and nothing else, so a test can make any one of them fail
/// (or "crash" the process at it) and prove no step can lose the file.
/// </summary>
/// <remarks>Failures are <see cref="IOException"/> (including <see cref="FileInUseException"/>) or <see cref="UnauthorizedAccessException"/>.</remarks>
public interface ISwapFileSystem
{
    bool FileExists(string path);

    /// <summary>The remux pass's source fingerprint (<see cref="SourceFiles.Fingerprint"/>): device, inode, size, mtime.</summary>
    SourceFingerprint Fingerprint(string path);

    /// <summary>Hard links to the file; <see langword="null"/> when the platform cannot say.</summary>
    int? LinkCount(string path);

    /// <summary>Whether the file itself refuses replacement (the Windows read-only attribute).</summary>
    bool IsReadOnly(string path);

    /// <summary>Bytes the current user may still write on the volume holding <paramref name="directory"/>; <see langword="null"/> when unknown.</summary>
    long? AvailableFreeBytes(string directory);

    /// <summary>Creates and removes a probe file in <paramref name="directory"/>; throws when that is not allowed.</summary>
    void ProbeWrite(string directory);

    /// <summary>Whether another program holds the file so that it cannot be renamed now.</summary>
    bool IsInUse(string path);

    /// <summary>Best effort: give <paramref name="destination"/> the permissions (and, where allowed, the owner) of <paramref name="source"/>. Never the timestamps.</summary>
    void CopyPermissions(string source, string destination);

    /// <summary>An atomic same-volume rename that never replaces an existing <paramref name="destination"/>.</summary>
    void Move(string source, string destination);

    /// <summary>Removes the file; a missing file is not an error.</summary>
    void Delete(string path);

    /// <summary>Every file under <paramref name="folder"/> (recursively) whose name is a swap leftover.</summary>
    IEnumerable<string> EnumerateLeftovers(string folder);
}

/// <summary>The real filesystem.</summary>
/// <remarks>
/// <para>
/// <b>Renames.</b> On Windows <see cref="Move"/> calls <c>MoveFileExW</c> with only <c>MOVEFILE_WRITE_THROUGH</c>: no
/// <c>MOVEFILE_REPLACE_EXISTING</c>, so a file that appeared at the destination (say, the manager importing a newer copy while
/// Weir worked) is never overwritten, and no <c>MOVEFILE_COPY_ALLOWED</c>, so a rename can never silently become a non-atomic
/// copy. <c>File.Replace</c> (<c>ReplaceFile</c>) was not used: it folds both renames of the commit into one call whose partial
/// failures (<c>ERROR_UNABLE_TO_MOVE_REPLACEMENT_2</c>) leave the same states as two renames, but hides which one happened.
/// Elsewhere <see cref="File.Move(string, string, bool)"/> without overwrite is used: .NET implements it with
/// <c>link</c> + <c>unlink</c> (falling back to an existence check and <c>rename</c> where links are unsupported), which also
/// refuses an existing destination.
/// </para>
/// <para>
/// <b>Link count.</b> <c>GetFileInformationByHandle</c>'s <c>nNumberOfLinks</c> on Windows (a handle opened for attributes only,
/// so it works on a file another program holds); <c>statx</c>'s <c>stx_nlink</c> on Linux. Other platforms report unknown.
/// </para>
/// <para>
/// <b>Permissions.</b> Windows: the file's DACL is copied (owner changes need privileges Weir does not ask for). POSIX: the mode
/// bits are copied, and the owner and group too when running as root. The modification time is deliberately not copied: the
/// manager's rescan uses size and mtime to notice the change.
/// </para>
/// </remarks>
public sealed partial class PhysicalSwapFileSystem : ISwapFileSystem
{
    private const int ErrorSharingViolation = 32;
    private const int ErrorLockViolation = 33;
    private const int Ebusy = 16;
    private const int Etxtbsy = 26;

    private const uint FileReadAttributes = 0x80;
    private const uint DeleteAccess = 0x00010000;
    private const uint FileShareAll = 0x1 | 0x2 | 0x4;
    private const uint OpenExisting = 3;
    private const uint FileFlagBackupSemantics = 0x02000000;
    private const uint MoveFileWriteThrough = 0x8;

    public static PhysicalSwapFileSystem Instance { get; } = new();

    public bool FileExists(string path) => File.Exists(path);

    public SourceFingerprint Fingerprint(string path) => SourceFiles.Fingerprint(path);

    public int? LinkCount(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            using var handle = OpenWindowsHandle(path, FileReadAttributes);
            return GetFileInformationByHandle(handle, out var information)
                ? (int)information.NumberOfLinks
                : throw WindowsError(Marshal.GetLastPInvokeError(), $"'{path}'");
        }

        return UnixStat(path) is { } stat ? (int)stat.Links : null;
    }

    public bool IsReadOnly(string path) =>
        OperatingSystem.IsWindows() && File.GetAttributes(path).HasFlag(FileAttributes.ReadOnly);

    public long? AvailableFreeBytes(string directory)
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                return GetDiskFreeSpaceExW(directory, out var available, out _, out _) ? (long)Math.Min(available, long.MaxValue) : null;
            }

            return new DriveInfo(directory).AvailableFreeSpace;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return null;
        }
    }

    public void ProbeWrite(string directory)
    {
        var probe = Path.Join(directory, $".weir-write-test-{Environment.ProcessId}-{Guid.NewGuid():N}");
        try
        {
            using var stream = new FileStream(probe, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1);
            stream.WriteByte(0);
        }
        finally
        {
            try
            {
                File.Delete(probe);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }
        }
    }

    public bool IsInUse(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            // POSIX renames are not blocked by open handles; EBUSY surfaces from Move itself.
            return false;
        }

        var handle = CreateFileW(path, DeleteAccess, FileShareAll, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics, IntPtr.Zero);
        if (!handle.IsInvalid)
        {
            handle.Dispose();
            return false;
        }

        var error = Marshal.GetLastPInvokeError();
        handle.Dispose();
        return error is ErrorSharingViolation or ErrorLockViolation ? true : throw WindowsError(error, $"'{path}'");
    }

    public void CopyPermissions(string source, string destination)
    {
        if (OperatingSystem.IsWindows())
        {
            // A security object read from a file persists nothing unless it is marked modified, so the DACL is copied into a
            // new one. Inherited entries in it are ignored by Windows and inherited afresh from the (same) folder.
            var read = new FileInfo(source).GetAccessControl(AccessControlSections.Access);
            var copy = new FileSecurity();
            copy.SetSecurityDescriptorBinaryForm(read.GetSecurityDescriptorBinaryForm(), AccessControlSections.Access);
            new FileInfo(destination).SetAccessControl(copy);
            return;
        }

        var mode = File.GetUnixFileMode(source);
        if (UnixIsRoot() && UnixStat(source) is { } stat && UnixChown(destination, stat.Uid, stat.Gid) != 0)
        {
            throw new IOException($"chown failed with errno {Marshal.GetLastPInvokeError()} for '{destination}'");
        }

        // After chown, which clears set-user-ID and set-group-ID bits.
        File.SetUnixFileMode(destination, mode);
    }

    public void Move(string source, string destination)
    {
        if (OperatingSystem.IsWindows())
        {
            if (!MoveFileExW(source, destination, MoveFileWriteThrough))
            {
                throw WindowsError(Marshal.GetLastPInvokeError(), $"'{source}' -> '{destination}'");
            }

            return;
        }

        try
        {
            File.Move(source, destination, overwrite: false);
        }
        catch (IOException exception) when (exception is not FileInUseException && exception.HResult is Ebusy or Etxtbsy)
        {
            throw new FileInUseException(exception.Message, exception);
        }
    }

    public void Delete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (IOException exception) when (exception is not FileInUseException && IsInUseError(exception))
        {
            throw new FileInUseException(exception.Message, exception);
        }
    }

    public IEnumerable<string> EnumerateLeftovers(string folder)
    {
        var options = new EnumerationOptions
        {
            RecurseSubdirectories = true,
            IgnoreInaccessible = true,
            MatchType = MatchType.Simple,
            MatchCasing = MatchCasing.CaseSensitive,
            // Never follow a link out of the library, and never skip a hidden leftover.
            AttributesToSkip = FileAttributes.ReparsePoint,
        };
        return Directory.EnumerateFiles(folder, "*.weir-*", options)
            .Where(path => SafeSwapRules.TryParseLeftover(path, out _, out _));
    }

    private static bool IsInUseError(IOException exception)
    {
        var code = OperatingSystem.IsWindows() ? exception.HResult & 0xFFFF : exception.HResult;
        return OperatingSystem.IsWindows() ? code is ErrorSharingViolation or ErrorLockViolation : code is Ebusy or Etxtbsy;
    }

    private static Exception WindowsError(int error, string subject) => error switch
    {
        ErrorSharingViolation or ErrorLockViolation => new FileInUseException($"{new Win32Exception(error).Message} ({subject})"),
        5 => new UnauthorizedAccessException($"{new Win32Exception(error).Message} ({subject})"),
        2 or 3 => new FileNotFoundException($"{new Win32Exception(error).Message} ({subject})"),
        _ => new IOException($"{new Win32Exception(error).Message} ({subject})", unchecked((int)0x80070000) | error),
    };

    private static SafeFileHandle OpenWindowsHandle(string path, uint access)
    {
        var handle = CreateFileW(path, access, FileShareAll, IntPtr.Zero, OpenExisting, FileFlagBackupSemantics, IntPtr.Zero);
        if (handle.IsInvalid)
        {
            var error = Marshal.GetLastPInvokeError();
            handle.Dispose();
            throw WindowsError(error, $"'{path}'");
        }

        return handle;
    }

    private readonly record struct UnixFileStat(uint Links, uint Uid, uint Gid);

    private static UnixFileStat? UnixStat(string path)
    {
        if (!OperatingSystem.IsLinux())
        {
            return null;
        }

        const int atFdCwd = -100;
        const uint statxNlink = 0x4;
        const uint statxUid = 0x8;
        const uint statxGid = 0x10;
        // struct statx is the same on every Linux architecture: stx_mask (u32) at 0, stx_nlink at 16, stx_uid at 20, stx_gid at 24.
        var buffer = new byte[256];
        try
        {
            if (Statx(atFdCwd, path, 0, statxNlink | statxUid | statxGid, ref buffer[0]) != 0)
            {
                var errno = Marshal.GetLastPInvokeError();
                throw errno == 2 ? new FileNotFoundException($"No such file: '{path}'", path) : new IOException($"statx failed with errno {errno} for '{path}'");
            }
        }
        catch (Exception exception) when (exception is DllNotFoundException or EntryPointNotFoundException)
        {
            return null;
        }

        var mask = BitConverter.ToUInt32(buffer, 0);
        if ((mask & statxNlink) == 0)
        {
            return null;
        }

        return new UnixFileStat(BitConverter.ToUInt32(buffer, 16), BitConverter.ToUInt32(buffer, 20), BitConverter.ToUInt32(buffer, 24));
    }

    private static bool UnixIsRoot()
    {
        try
        {
            return Geteuid() == 0;
        }
        catch (Exception exception) when (exception is DllNotFoundException or EntryPointNotFoundException)
        {
            return false;
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ByHandleFileInformation
    {
        public uint FileAttributes;
        public uint CreationTimeLow;
        public uint CreationTimeHigh;
        public uint LastAccessTimeLow;
        public uint LastAccessTimeHigh;
        public uint LastWriteTimeLow;
        public uint LastWriteTimeHigh;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }

    [LibraryImport("kernel32.dll", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    private static partial SafeFileHandle CreateFileW(
        string fileName,
        uint desiredAccess,
        uint shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile);

    [LibraryImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetFileInformationByHandle(SafeFileHandle file, out ByHandleFileInformation information);

    [LibraryImport("kernel32.dll", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool MoveFileExW(string existingFileName, string newFileName, uint flags);

    [LibraryImport("kernel32.dll", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetDiskFreeSpaceExW(string directoryName, out ulong freeBytesAvailableToCaller, out ulong totalBytes, out ulong totalFreeBytes);

    [LibraryImport("libc", EntryPoint = "statx", SetLastError = true, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int Statx(int directoryFd, string path, int flags, uint mask, ref byte buffer);

    [LibraryImport("libc", EntryPoint = "geteuid")]
    private static partial uint Geteuid();

    [LibraryImport("libc", EntryPoint = "chown", SetLastError = true, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int UnixChown(string path, uint owner, uint group);
}
