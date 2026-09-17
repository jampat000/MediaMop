using Microsoft.Data.Sqlite;

namespace Weir.Infrastructure.Tests;

/// <summary>A temporary directory removed after the test, with SQLite's pooled handles released first.</summary>
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
        SqliteConnection.ClearAllPools();
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
    /// <summary>The checked-in Alembic-head reference, copied next to the test assembly.</summary>
    public static string AlembicHeadReference => Path.Join(AppContext.BaseDirectory, "schema", "alembic-head.sql");

    /// <summary>The repository root, found by walking up from the test assembly.</summary>
    public static string? RepositoryRoot
    {
        get
        {
            for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            {
                if (Directory.Exists(Path.Join(directory.FullName, "apps", "server")) &&
                    Directory.Exists(Path.Join(directory.FullName, "apps", "backend")))
                {
                    return directory.FullName;
                }
            }

            return null;
        }
    }
}
