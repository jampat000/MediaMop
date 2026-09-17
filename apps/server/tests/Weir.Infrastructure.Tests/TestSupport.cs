namespace Weir.Infrastructure.Tests;

/// <summary>
/// A temporary directory removed after the test. A caller that opened a <c>SqliteDatabase</c> inside it
/// must release that database's own pooled connections itself (<c>SqliteDatabase.ClearPool()</c>) before
/// this runs; deleting no longer clears every pool in the process, which would race with any other
/// test's connections still open at the same time.
/// </summary>
internal sealed class TempDirectory : IDisposable
{
    public TempDirectory()
    {
        Path = System.IO.Path.Join(System.IO.Path.GetTempPath(), "weir-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path);
    }

    public string Path { get; }

    public string Join(params string[] parts) => System.IO.Path.Join([Path, .. parts]);

    public void Dispose()
    {
        for (var attempt = 0; attempt < 5; attempt++)
        {
            try
            {
                Directory.Delete(Path, recursive: true);
                return;
            }
            catch (IOException) when (attempt < 4)
            {
                Thread.Sleep(100);
            }
            catch (UnauthorizedAccessException) when (attempt < 4)
            {
                Thread.Sleep(100);
            }
            catch (IOException)
            {
                return;
            }
            catch (UnauthorizedAccessException)
            {
                return;
            }
        }
    }
}

internal static class RepositoryPaths
{
    /// <summary>
    /// The checked-in schema reference, copied next to the test assembly: the schema and seed rows the
    /// retired Python backend's last Alembic migration created, which the .NET migrations were proven to
    /// reproduce exactly. It is frozen history now; the .NET migrations are the schema's only source.
    /// </summary>
    public static string AlembicHeadReference => Path.Join(AppContext.BaseDirectory, "schema", "alembic-head.sql");

    /// <summary>The repository root, found by walking up from the test assembly.</summary>
    public static string? RepositoryRoot
    {
        get
        {
            for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            {
                if (Directory.Exists(Path.Join(directory.FullName, "apps", "server")) &&
                    Directory.Exists(Path.Join(directory.FullName, "apps", "web")))
                {
                    return directory.FullName;
                }
            }

            return null;
        }
    }
}

/// <summary>
/// <see cref="Weir.Infrastructure.Tests.Jobs.ClaimConcurrencyTests"/> and
/// <see cref="Weir.Infrastructure.Tests.Jobs.LeaseRenewalTests"/> each block many thread-pool
/// threads at once (parallel SQLite claims behind a barrier, or a real-clock lease heartbeat under
/// <c>Task.Delay</c>). This collection keeps those two classes from running at the same time as each
/// other, so their thread-pool pressure and real-time assumptions don't compound.
/// </summary>
/// <remarks>
/// <c>DisableParallelization</c> only serializes the members of <em>this</em> collection against each
/// other; xUnit still runs every other (default, per-class) collection in the assembly concurrently with
/// it, so this alone does not give these tests exclusive use of the process. The cross-test flakiness
/// that used to surface here (an unrelated test's teardown calling the process-wide
/// <c>SqliteConnection.ClearAllPools()</c> while these tests had connections mid-transaction) is fixed at
/// its source instead: every test now releases only its own database's pool
/// (<see cref="Weir.Infrastructure.Sqlite.SqliteDatabase.ClearPool"/>), so no test's teardown can disturb
/// another test's live connection regardless of what runs alongside it.
/// </remarks>
[CollectionDefinition(Name, DisableParallelization = true)]
public sealed class SerialTestGroup
{
    public const string Name = "Serial: thread-pool heavy";
}
