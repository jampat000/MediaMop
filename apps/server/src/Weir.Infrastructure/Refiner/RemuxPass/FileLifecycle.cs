using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Weir.Infrastructure.MediaManagers;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>A free-space check before a write-heavy step (<c>DiskSpaceCheck</c>).</summary>
public sealed record DiskSpaceCheck(bool Ok, string CheckedPath, double FreeMb, long RequiredMb, string Message);

/// <summary>
/// Recoverable file writes and moves for media mutations (port of <c>platform/file_lifecycle/mutations.py</c> and
/// <c>guardrails.py</c>): nothing partial is ever exposed at a final path.
/// </summary>
public static partial class FileLifecycle
{
    private const int CopyChunkBytes = 8 * 1024 * 1024;
    private const long BytesPerMib = 1024 * 1024;

    /// <summary><c>bytes_to_mb</c>.</summary>
    public static double BytesToMb(long sizeBytes) => Math.Max(0.0, sizeBytes / (double)BytesPerMib);

    /// <summary><c>nearest_existing_parent</c>: the path itself when it is an existing directory, else its closest existing ancestor.</summary>
    public static string NearestExistingParent(string path)
    {
        var current = Directory.Exists(path) ? path : Path.GetDirectoryName(path) ?? path;
        while (!Directory.Exists(current) && !File.Exists(current))
        {
            var parent = Path.GetDirectoryName(current);
            if (parent is null || parent == current)
            {
                return current;
            }

            current = parent;
        }

        return current;
    }

    /// <summary><c>check_minimum_free_disk_space</c>. A requirement of zero turns the check off.</summary>
    public static DiskSpaceCheck CheckMinimumFreeDiskSpace(string targetPath, long requiredMb, Func<string, long>? freeBytes = null)
    {
        var required = Math.Max(0, requiredMb);
        var checkedPath = NearestExistingParent(targetPath);
        if (required <= 0)
        {
            return new DiskSpaceCheck(true, checkedPath, 0.0, 0, "Disk-space guardrail disabled.");
        }

        var free = BytesToMb((freeBytes ?? AvailableFreeBytes)(checkedPath));
        var ok = free >= required;
        var message = ok
            ? $"Target drive has enough free space ({free.ToString("F1", CultureInfo.InvariantCulture)} MB >= {required.ToString(CultureInfo.InvariantCulture)} MB required)."
            : $"Skipped: insufficient disk space on target drive ({(free / 1024).ToString("F1", CultureInfo.InvariantCulture)} GB < {(required / 1024.0).ToString("F1", CultureInfo.InvariantCulture)} GB required).";
        return new DiskSpaceCheck(ok, checkedPath, free, required, message);
    }

    private static long AvailableFreeBytes(string path) => new DriveInfo(Path.GetFullPath(path)).AvailableFreeSpace;

    /// <summary>
    /// <c>safe_copy_to_final</c>: copy into a hidden <c>.{name}.XXXXXXXX.partial</c> beside the destination, validate it,
    /// then atomically replace the destination. A failed copy or validation leaves nothing behind.
    /// </summary>
    public static async Task SafeCopyToFinalAsync(
        string source,
        string final,
        Func<string, Task>? validateStaged = null,
        Action<long, long>? progressCallback = null,
        bool preserveMetadata = true)
    {
        var src = Path.GetFullPath(source);
        var directory = Path.GetDirectoryName(Path.GetFullPath(final))!;
        Directory.CreateDirectory(directory);
        var tmp = CreateTempFile(directory, "." + Path.GetFileName(final) + ".", ".partial");
        try
        {
            var total = new FileInfo(src).Length;
            long copied = 0;
            using (var input = new FileStream(src, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1, FileOptions.SequentialScan))
            using (var output = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None, 1))
            {
                var buffer = new byte[Math.Min(CopyChunkBytes, Math.Max(4096, total))];
                int read;
                while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
                {
                    output.Write(buffer, 0, read);
                    copied += read;
                    if (progressCallback is not null)
                    {
                        try
                        {
                            progressCallback(copied, total);
                        }
#pragma warning disable CA1031 // Progress is optional observability; it must never invalidate a safe copy.
                        catch (Exception)
#pragma warning restore CA1031
                        {
                        }
                    }
                }
            }

            if (preserveMetadata)
            {
                File.SetLastWriteTimeUtc(tmp, File.GetLastWriteTimeUtc(src));
                File.SetLastAccessTimeUtc(tmp, File.GetLastAccessTimeUtc(src));
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            BestEffortDelete(tmp);
            throw new FileLifecycleException($"Could not safely copy {src} to {final}: {exception.Message}", exception);
        }

        if (validateStaged is not null)
        {
            try
            {
                await validateStaged(tmp).ConfigureAwait(false);
            }
            catch
            {
                BestEffortDelete(tmp);
                throw;
            }
        }

        try
        {
            File.Move(tmp, final, overwrite: true);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            BestEffortDelete(tmp);
            throw new FileLifecycleException($"Could not safely publish the validated copy at {final}: {exception.Message}", exception);
        }
    }

    /// <summary>
    /// <c>try_hardlink_to_final</c>: validate and atomically expose a same-volume hard link. False means the link was refused
    /// and the caller should copy; validation and publication errors still throw.
    /// </summary>
    public static async Task<bool> TryHardlinkToFinalAsync(string source, string final, Func<string, Task>? validateStaged = null)
    {
        var src = Path.GetFullPath(source);
        var directory = Path.GetDirectoryName(Path.GetFullPath(final))!;
        Directory.CreateDirectory(directory);
        var tmp = CreateTempFile(directory, "." + Path.GetFileName(final) + ".", ".link");
        BestEffortDelete(tmp);
        if (!CreateHardLink(tmp, src))
        {
            BestEffortDelete(tmp);
            return false;
        }

        try
        {
            if (validateStaged is not null)
            {
                await validateStaged(tmp).ConfigureAwait(false);
            }

            File.Move(tmp, final, overwrite: true);
        }
        catch
        {
            BestEffortDelete(tmp);
            throw;
        }

        return true;
    }

    /// <summary>
    /// <c>safe_finalize_file</c>: a rename when it can be one; across volumes, a copy into a hidden partial beside the
    /// destination, an atomic replace, then removal of the staged file.
    /// </summary>
    public static void SafeFinalizeFile(string staged, string final)
    {
        var src = Path.GetFullPath(staged);
        var directory = Path.GetDirectoryName(Path.GetFullPath(final))!;
        Directory.CreateDirectory(directory);
        try
        {
            File.Move(src, final, overwrite: true);
            return;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            // Fall through to the copy.
        }

        var tmp = CreateTempFile(directory, "." + Path.GetFileName(final) + ".", ".partial");
        try
        {
            File.Copy(src, tmp, overwrite: true);
            File.Move(tmp, final, overwrite: true);
            BestEffortDelete(src);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            BestEffortDelete(tmp);
            throw new FileLifecycleException($"Could not safely finalize {src} to {final}: {exception.Message}", exception);
        }
    }

    /// <summary><c>tempfile.mkstemp</c>: a new file named prefix + 8 random characters + suffix, created exclusively.</summary>
    public static string CreateTempFile(string directory, string prefix, string suffix)
    {
        const string Characters = "abcdefghijklmnopqrstuvwxyz0123456789_";
        for (var attempt = 0; ; attempt++)
        {
            var path = Path.GetFullPath(Path.Combine(directory, prefix + RandomNumberGenerator.GetString(Characters, 8) + suffix));
            try
            {
                using (new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None))
                {
                }

                return path;
            }
            catch (IOException) when (attempt < 100 && File.Exists(path))
            {
                // Name taken; draw again.
            }
        }
    }

    /// <summary><c>_best_effort_unlink</c>.</summary>
    public static void BestEffortDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
        }
    }

    /// <summary><c>os.link</c>. False when the platform or volume refuses.</summary>
    public static bool CreateHardLink(string link, string existing)
    {
        if (OperatingSystem.IsWindows())
        {
            return CreateHardLinkW(link, existing, IntPtr.Zero);
        }

        try
        {
            return UnixLink(existing, link) == 0;
        }
        catch (Exception exception) when (exception is DllNotFoundException or EntryPointNotFoundException)
        {
            return false;
        }
    }

    [LibraryImport("kernel32.dll", EntryPoint = "CreateHardLinkW", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool CreateHardLinkW(string newFileName, string existingFileName, IntPtr securityAttributes);

    [LibraryImport("libc", EntryPoint = "link", SetLastError = true, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int UnixLink(string existing, string link);
}
