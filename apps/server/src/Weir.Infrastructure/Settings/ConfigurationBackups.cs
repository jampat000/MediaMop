using System.Globalization;
using System.Text;
using Microsoft.Data.Sqlite;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Settings;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Settings;

/// <summary>A <c>suite_configuration_backup</c> row.</summary>
public sealed record ConfigurationBackupRecord(long Id, PyDateTime CreatedAt, string FileName, long SizeBytes);

/// <summary>
/// Automatic configuration snapshots on disk (port of <c>suite_configuration_backup_service</c> and the
/// tick in <c>suite_configuration_backup_periodic</c>).
/// </summary>
public sealed class ConfigurationBackups
{
    public const int MaxFiles = 5;

    private readonly WeirOptions _options;
    private readonly TimeProvider _time;
    private readonly ITimeZoneResolver _zones;

    public ConfigurationBackups(WeirOptions options, TimeProvider time, ITimeZoneResolver zones)
    {
        _options = options;
        _time = time;
        _zones = zones;
    }

    /// <summary><c>{backup_dir}/suite-configuration</c>, resolved.</summary>
    public string Directory => Path.GetFullPath(Path.Join(_options.BackupDir, "suite-configuration"));

    public static Task<List<ConfigurationBackupRecord>> ListAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QueryAsync(
            "SELECT id, created_at, file_name, size_bytes FROM suite_configuration_backup " +
            "ORDER BY suite_configuration_backup.created_at DESC, suite_configuration_backup.id DESC",
            Read);
    }

    public static PyDict ItemOut(ConfigurationBackupRecord row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return new PyDict()
            .Set("id", row.Id)
            .Set("created_at", row.CreatedAt.PydanticJson())
            .Set("file_name", row.FileName)
            .Set("size_bytes", row.SizeBytes);
    }

    /// <summary><c>get_suite_configuration_backup_file_path</c>. Throws <see cref="PyValueErrorException"/> (answered as 404).</summary>
    public async Task<(string Path, ConfigurationBackupRecord Row)> GetFileAsync(UnitOfWork uow, long backupId)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var row = await uow.QuerySingleAsync(
            "SELECT id, created_at, file_name, size_bytes FROM suite_configuration_backup WHERE suite_configuration_backup.id = $id",
            Read,
            ("$id", backupId)).ConfigureAwait(false) ?? throw new PyValueErrorException("Configuration snapshot not found.");
        if (PurePathName(row.FileName) != row.FileName || !row.FileName.StartsWith("suite-configuration-", StringComparison.Ordinal))
        {
            throw new PyValueErrorException("Configuration snapshot file name is invalid.");
        }

        var root = Directory;
        var path = Path.GetFullPath(Path.Join(root, row.FileName));
        var relative = Path.GetRelativePath(root, path);
        if (relative == ".." || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal) || Path.IsPathRooted(relative))
        {
            throw new PyValueErrorException("Configuration snapshot path is outside the backup directory.");
        }

        if (!File.Exists(path))
        {
            throw new PyValueErrorException("Configuration snapshot file is missing on disk.");
        }

        return (path, row);
    }

    /// <summary><c>create_suite_configuration_backup</c>.</summary>
    public async Task<ConfigurationBackupRecord> CreateAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var root = Directory;
        System.IO.Directory.CreateDirectory(root);
        var now = PyDateTime.UtcNow(_time);
        var bundle = await ConfigurationBundleStore.BuildAsync(uow).ConfigureAwait(false);
        var stamp = now.Clock.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture);
        var fileName = $"suite-configuration-{stamp}.json";
        var path = Path.Join(root, fileName);
        for (var i = 1; File.Exists(path); i++)
        {
            fileName = $"suite-configuration-{stamp}-{i}.json";
            path = Path.Join(root, fileName);
        }

        var payload = Encoding.UTF8.GetBytes(PyJsonWriter.Dumps(bundle, PyJsonFormat.IndentedSorted));
        await File.WriteAllBytesAsync(path, payload).ConfigureAwait(false);
        var id = await uow.ExecuteScalarWriteAsync(
            "INSERT INTO suite_configuration_backup (created_at, file_name, size_bytes) VALUES ($created, $name, $size) RETURNING id",
            ("$created", now.ToSqlite()),
            ("$name", fileName),
            ("$size", payload.LongLength)).ConfigureAwait(false);
        await PruneAsync(uow).ConfigureAwait(false);
        return new ConfigurationBackupRecord(Convert.ToInt64(id, CultureInfo.InvariantCulture), now, fileName, payload.LongLength);
    }

    /// <summary><c>run_suite_configuration_backup_tick</c>: 1 when a snapshot was written.</summary>
    public async Task<int> RunTickAsync(SqliteDatabase database, DateTime? nowUtc = null, CancellationToken cancellationToken = default)
    {
        var when = nowUtc ?? _time.GetUtcNow().UtcDateTime;
        var uow = await UnitOfWork.OpenAsync(database, cancellationToken).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            var suite = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
            if (!ConfigurationBackupSchedule.IsDue(suite, when, _zones))
            {
                await uow.CommitAsync().ConfigureAwait(false);
                return 0;
            }

            await CreateAsync(uow).ConfigureAwait(false);
            await SuiteSettingsStore.UpdateAsync(
                uow, suite, suite with { ConfigurationBackupLastRunAt = PyDateTime.FromUtc(PyDateTime.TruncateToMicroseconds(when)) }).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
            return 1;
        }
    }

    private async Task PruneAsync(UnitOfWork uow)
    {
        var rows = await ListAsync(uow).ConfigureAwait(false);
        var drop = rows.Skip(MaxFiles).ToList();
        if (drop.Count == 0)
        {
            return;
        }

        var root = Directory;
        var keep = rows.Take(MaxFiles).Select(r => r.FileName).ToHashSet(StringComparer.Ordinal);
        foreach (var row in drop)
        {
            TryDelete(Path.Join(root, row.FileName));
            await uow.ExecuteAsync("DELETE FROM suite_configuration_backup WHERE suite_configuration_backup.id = $id", ("$id", row.Id)).ConfigureAwait(false);
        }

        if (System.IO.Directory.Exists(root))
        {
            foreach (var file in System.IO.Directory.EnumerateFiles(root, "suite-configuration-*.json"))
            {
                if (!keep.Contains(Path.GetFileName(file)))
                {
                    TryDelete(file);
                }
            }
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            // contextlib.suppress(OSError), as in Python.
        }
    }

    /// <summary><c>Path(name).name</c>.</summary>
    private static string PurePathName(string name)
    {
        var separators = OperatingSystem.IsWindows() ? new[] { '/', '\\' } : ['/'];
        var trimmed = name.TrimEnd(separators);
        var last = trimmed.LastIndexOfAny(separators);
        var tail = last < 0 ? trimmed : trimmed[(last + 1)..];
        if (OperatingSystem.IsWindows() && tail.Length >= 2 && tail[1] == ':')
        {
            tail = tail[2..];
        }

        return tail is "." ? string.Empty : tail;
    }

    private static ConfigurationBackupRecord Read(SqliteDataReader reader) => new(
        SqliteValues.GetInt64(reader, 0),
        SqliteValues.GetDateTime(reader, 1),
        SqliteValues.GetString(reader, 2),
        SqliteValues.GetInt64(reader, 3));
}
