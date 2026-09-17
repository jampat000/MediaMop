using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using Weir.Core.Json;

namespace Weir.Infrastructure.Browse;

/// <summary>A failure the endpoint answers with this status and detail.</summary>
public sealed class DirectoryBrowseException : Exception
{
    public DirectoryBrowseException()
    {
    }

    public DirectoryBrowseException(string message)
        : base(message)
    {
    }

    public DirectoryBrowseException(string message, Exception innerException)
        : base(message, innerException)
    {
    }

    public DirectoryBrowseException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public DirectoryBrowseException(int statusCode, string message, Exception innerException)
        : base(message, innerException)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; }
}

/// <summary>Server-side folder browsing for path settings (port of <c>weir.platform.local_browse.router</c>).</summary>
public static partial class DirectoryBrowser
{
    public static PyDict Browse(string? path)
    {
        if (path is null || path.Trim().Length == 0)
        {
            return Out(null, null, RootEntries());
        }

        var sanitized = path.Replace("\0", string.Empty, StringComparison.Ordinal);
        if (!IsAbsolute(sanitized))
        {
            throw new DirectoryBrowseException(400, "Path must be absolute.");
        }

        var normalized = RealPath(sanitized);
        if (OperatingSystem.IsWindows())
        {
            normalized = normalized.TrimEnd('\\', '/') + "\\";
            if (!ValidWindowsRoots().Any(root => normalized == root || normalized.StartsWith(root, StringComparison.Ordinal)))
            {
                throw new DirectoryBrowseException(400, "Path is not within a valid drive root.");
            }
        }
        else if (!normalized.StartsWith('/'))
        {
            throw new DirectoryBrowseException(400, "Path must begin at the filesystem root.");
        }

        if (!Directory.Exists(normalized))
        {
            throw new DirectoryBrowseException(404, "The requested directory does not exist.");
        }

        var parent = ParentOf(normalized);
        string? parentPath = parent != normalized ? parent : null;
        if (OperatingSystem.IsWindows() && !string.IsNullOrEmpty(parentPath))
        {
            parentPath = parentPath.TrimEnd('\\', '/') + "\\";
        }

        var entries = new List<(string Name, PyDict Entry)>();
        try
        {
            foreach (var child in Directory.EnumerateFileSystemEntries(normalized))
            {
                if (!Directory.Exists(child))
                {
                    continue;
                }

                var name = Path.GetFileName(child.TrimEnd(Path.DirectorySeparatorChar));
                var childPath = RealPath(NormalizeDirectoryPath(child));
                entries.Add((name, new PyDict()
                    .Set("name", name.Length == 0 ? child : name)
                    .Set("path", childPath)
                    .Set("kind", "directory")
                    .Set("description", (string?)null)));
            }
        }
        catch (UnauthorizedAccessException exception)
        {
            throw new DirectoryBrowseException(403, "Weir cannot access this folder.", exception);
        }
        catch (IOException exception)
        {
            throw new DirectoryBrowseException(400, "The requested directory cannot be accessed.", exception);
        }

        var sorted = entries.OrderBy(e => e.Name.ToLowerInvariant(), StringComparer.Ordinal).Select(e => e.Entry).ToList();
        return Out(normalized, parentPath, sorted);
    }

    private static PyDict Out(string? current, string? parent, IEnumerable<PyDict> entries) => new PyDict()
        .Set("current_path", current)
        .Set("parent_path", parent)
        .Set("entries", new PyList(entries));

    private static List<PyDict> RootEntries()
    {
        if (!OperatingSystem.IsWindows())
        {
            return [Entry("/", "/", "root", "Filesystem root")];
        }

        var entries = new List<PyDict>();
        foreach (var letter in Enumerable.Range('A', 26).Select(c => (char)c))
        {
            var root = $"{letter}:\\";
            if (!Directory.Exists(root))
            {
                continue;
            }

            string description;
            try
            {
                description = (int)new DriveInfo(root).DriveType switch
                {
                    2 => "External drive",
                    3 => "Local drive",
                    4 => "Network drive",
                    5 => "Optical drive",
                    6 => "RAM disk",
                    _ => "Drive",
                };
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException)
            {
                description = "Drive";
            }

            entries.Add(Entry(root.TrimEnd('\\'), root, "root", description));
        }

        return entries;
    }

    private static PyDict Entry(string name, string path, string kind, string? description) => new PyDict()
        .Set("name", name)
        .Set("path", path)
        .Set("kind", kind)
        .Set("description", description);

    private static List<string> ValidWindowsRoots() =>
        [.. Enumerable.Range('A', 26).Select(c => $"{(char)c}:\\").Where(Directory.Exists)];

    /// <summary><c>_normalize_directory_path</c>.</summary>
    private static string NormalizeDirectoryPath(string path)
    {
        var sanitized = path.Replace("\0", string.Empty, StringComparison.Ordinal);
        if (!IsAbsolute(sanitized))
        {
            throw new DirectoryBrowseException(400, "Path must be absolute.");
        }

        var value = RealPath(sanitized);
        if (OperatingSystem.IsWindows())
        {
            value = value.TrimEnd('\\', '/') + "\\";
            if (!ValidWindowsRoots().Any(root => value == root || value.StartsWith(root, StringComparison.Ordinal)))
            {
                throw new DirectoryBrowseException(400, "Path is not within a valid drive root.");
            }

            return value;
        }

        return value.StartsWith('/') ? value : throw new DirectoryBrowseException(400, "Path must begin at the filesystem root.");
    }

    /// <summary><c>os.path.isabs</c> (Python 3.11: on Windows a leading separator counts).</summary>
    private static bool IsAbsolute(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            return path.StartsWith('/');
        }

        var head = path.Length > 3 ? path[..3] : path;
        head = head.Replace('/', '\\');
        return head.StartsWith('\\') || (head.Length >= 3 && head[1..3] == ":\\");
    }

    /// <summary><c>Path(p).parent</c> as a string.</summary>
    private static string ParentOf(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            var trimmed = path.TrimEnd('\\');
            if (trimmed.Length <= 2 && trimmed.EndsWith(':'))
            {
                return trimmed + "\\";
            }

            var parent = Path.GetDirectoryName(trimmed + (trimmed.EndsWith(':') ? "\\" : string.Empty));
            return parent ?? path;
        }

        if (path == "/")
        {
            return "/";
        }

        var unixParent = Path.GetDirectoryName(path.TrimEnd('/'));
        return string.IsNullOrEmpty(unixParent) ? "/" : unixParent;
    }

    /// <summary><c>os.path.realpath</c>: absolute, normalised, links resolved where the path exists.</summary>
    internal static string RealPath(string path)
    {
        var full = Path.GetFullPath(path);
        if (OperatingSystem.IsWindows())
        {
            return WindowsFinalPath(full) ?? TrimTrailing(full);
        }

        return UnixRealPath(full);
    }

    private static string TrimTrailing(string full)
    {
        var root = Path.GetPathRoot(full) ?? string.Empty;
        return full.Length > root.Length ? full.TrimEnd(Path.DirectorySeparatorChar) : full;
    }

    private static string UnixRealPath(string full)
    {
        var parts = full.Split('/', StringSplitOptions.RemoveEmptyEntries);
        var current = "/";
        foreach (var part in parts)
        {
            var next = current == "/" ? "/" + part : current + "/" + part;
            try
            {
                var info = new FileInfo(next);
                if (info.LinkTarget is not null)
                {
                    var target = info.ResolveLinkTarget(returnFinalTarget: true);
                    next = target is null ? next : Path.GetFullPath(target.FullName);
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                // Unresolvable links stay as written, as realpath does.
            }

            current = next;
        }

        return current;
    }

    private static string? WindowsFinalPath(string full)
    {
        const uint fileReadAttributes = 0x80;
        const uint shareAll = 0x7;
        const uint openExisting = 3;
        const uint backupSemantics = 0x02000000;
        using var handle = CreateFileW(full, fileReadAttributes, shareAll, IntPtr.Zero, openExisting, backupSemantics, IntPtr.Zero);
        if (handle.IsInvalid)
        {
            return null;
        }

        var buffer = new char[32768];
        uint length;
        unsafe
        {
            fixed (char* pointer = buffer)
            {
                length = GetFinalPathNameByHandleW(handle, pointer, (uint)buffer.Length, 0);
            }
        }

        if (length == 0 || length >= buffer.Length)
        {
            return null;
        }

        var result = new string(buffer, 0, (int)length);
        if (result.StartsWith(@"\\?\UNC\", StringComparison.Ordinal))
        {
            result = @"\\" + result[8..];
        }
        else if (result.StartsWith(@"\\?\", StringComparison.Ordinal))
        {
            result = result[4..];
        }

        return TrimTrailing(result);
    }

    [LibraryImport("kernel32.dll", EntryPoint = "CreateFileW", SetLastError = true, StringMarshalling = StringMarshalling.Utf16)]
    private static partial SafeFileHandle CreateFileW(
        string fileName, uint desiredAccess, uint shareMode, IntPtr securityAttributes, uint creationDisposition, uint flagsAndAttributes, IntPtr template);

    [LibraryImport("kernel32.dll", EntryPoint = "GetFinalPathNameByHandleW", SetLastError = true)]
    private static unsafe partial uint GetFinalPathNameByHandleW(SafeFileHandle file, char* path, uint pathLength, uint flags);
}
