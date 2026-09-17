using Weir.Core.Configuration;

namespace Weir.Infrastructure.Runtime;

/// <summary>
/// Startup checks on the runtime paths (port of <c>ensure_runtime_directories</c> and
/// <c>assert_sqlite_db_location_usable</c>), with the same operator messages.
/// </summary>
public static class RuntimeDirectories
{
    /// <summary>Create the backup, log and temp directories and the database's parent (idempotent).</summary>
    public static void Ensure(WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        Directory.CreateDirectory(options.BackupDir);
        Directory.CreateDirectory(options.LogDir);
        Directory.CreateDirectory(options.TempDir);
        var parent = Path.GetDirectoryName(options.DbPath);
        if (!string.IsNullOrEmpty(parent))
        {
            Directory.CreateDirectory(parent);
        }
    }

    /// <summary>
    /// Fail fast when the SQLite path cannot be used read-write: a directory at that path, a
    /// non-regular file, a parent that does not allow creating files, or an existing file that
    /// cannot be opened for writing. Call after <see cref="Ensure"/>.
    /// </summary>
    public static void AssertSqliteDbLocationUsable(string dbPath)
    {
        ArgumentException.ThrowIfNullOrEmpty(dbPath);
        var resolved = Path.GetFullPath(dbPath);
        if (Directory.Exists(resolved))
        {
            throw new WeirConfigurationException(
                $"SQLite database path must be a file, not a directory: {resolved}. " +
                "Fix WEIR_DB_PATH or remove the directory at that location.");
        }

        // Python also rejects special files (FIFOs, sockets) with "must be a regular file"; .NET has
        // no portable file-type check, so such a path fails below as "not writable" or at open.
        var parent = Path.GetDirectoryName(resolved) ?? resolved;
        try
        {
            var probe = Path.Join(parent, $"tmp{Guid.NewGuid():N}");
            using (new FileStream(probe, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None, 1, FileOptions.DeleteOnClose))
            {
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            throw new WeirConfigurationException(
                $"Cannot create files under database directory (check permissions and disk): {parent}", exception);
        }

        if (File.Exists(resolved))
        {
            try
            {
                using (new FileStream(resolved, FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite | FileShare.Delete))
                {
                }
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                throw new WeirConfigurationException(
                    $"SQLite database file exists but is not writable: {resolved}", exception);
            }
        }
    }
}
