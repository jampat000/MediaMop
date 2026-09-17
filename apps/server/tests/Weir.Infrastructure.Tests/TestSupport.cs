using System.Diagnostics;
using System.Text.Json;

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

/// <summary>A fact that runs only where the Python backend can be run (cross-checks against the reference).</summary>
[AttributeUsage(AttributeTargets.Method)]
internal sealed class PythonFactAttribute : FactAttribute
{
    public PythonFactAttribute()
    {
        if (PythonBackend.Executable is null || PythonBackend.SourceRoot is null)
        {
            Skip = "The Python backend virtualenv (apps/backend/.venv) was not found; set WEIR_TEST_PYTHON to run the Python cross-checks.";
        }
    }
}

/// <summary>Finds and runs the Python reference backend, importing this checkout's <c>apps/backend/src</c>.</summary>
internal static class PythonBackend
{
    /// <summary>This checkout's <c>apps/backend/src</c>: the code the cross-checks import.</summary>
    public static string? SourceRoot =>
        RepositoryPaths.RepositoryRoot is { } root && Directory.Exists(Path.Join(root, "apps", "backend", "src", "weir"))
            ? Path.Join(root, "apps", "backend", "src")
            : null;

    /// <summary><c>WEIR_TEST_PYTHON</c>, else this checkout's backend virtualenv, else the main checkout's for a worktree.</summary>
    public static string? Executable
    {
        get
        {
            var configured = Environment.GetEnvironmentVariable("WEIR_TEST_PYTHON");
            if (!string.IsNullOrWhiteSpace(configured))
            {
                return File.Exists(configured) ? configured : null;
            }

            if (RepositoryPaths.RepositoryRoot is not { } root)
            {
                return null;
            }

            var roots = new List<string> { root };
            // A git worktree under .claude/worktrees has no virtualenv of its own; use the main checkout's.
            var marker = Path.Join(".claude", "worktrees");
            var index = root.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (index > 0)
            {
                roots.Add(root[..index].TrimEnd('/', '\\'));
            }

            return roots
                .SelectMany(candidate => new[]
                {
                    Path.Join(candidate, "apps", "backend", ".venv", "Scripts", "python.exe"),
                    Path.Join(candidate, "apps", "backend", ".venv", "bin", "python"),
                })
                .FirstOrDefault(File.Exists);
        }
    }

    /// <summary>Run <paramref name="code"/>; returns stdout. Fails the test with stderr on a non-zero exit.</summary>
    public static string Run(string code, IReadOnlyDictionary<string, string> environment)
    {
        var start = new ProcessStartInfo(Executable!)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            UseShellExecute = false,
            WorkingDirectory = Path.GetDirectoryName(SourceRoot!)!,
        };
        start.ArgumentList.Add("-");
        foreach (var key in start.Environment.Keys.Where(k => k.StartsWith("WEIR_", StringComparison.OrdinalIgnoreCase)).ToList())
        {
            start.Environment.Remove(key);
        }

        start.Environment["PYTHONPATH"] = SourceRoot!;
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        start.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        foreach (var (key, value) in environment)
        {
            start.Environment[key] = value;
        }

        using var process = Process.Start(start)!;
        process.StandardInput.Write(
            "import weir.core.config as _config\n_config._load_backend_dotenv_if_present = lambda: None\n" + code);
        process.StandardInput.Close();
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        if (!process.WaitForExit(180_000))
        {
            process.Kill(entireProcessTree: true);
            Assert.Fail("The Python cross-check timed out.");
        }

        Assert.True(process.ExitCode == 0, "Python failed:\n" + stderr.Result + stdout.Result);
        return stdout.Result.Trim();
    }

    /// <summary>Run the queue driver (<c>Jobs/python_queue_driver.py</c>) over <paramref name="ops"/> against one database.</summary>
    public static async Task<JsonElement[]> RunAsync(string dbPath, string workDirectory, params object[] ops)
    {
        var opsPath = Path.Join(workDirectory, $"ops-{Guid.NewGuid():N}.json");
        await File.WriteAllTextAsync(opsPath, JsonSerializer.Serialize(ops));
        var start = new ProcessStartInfo(Executable!)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        start.ArgumentList.Add(Path.Join(AppContext.BaseDirectory, "Jobs", "python_queue_driver.py"));
        start.ArgumentList.Add(SourceRoot!);
        start.ArgumentList.Add(dbPath);
        start.ArgumentList.Add(opsPath);
        start.Environment["PYTHONPATH"] = SourceRoot!;
        start.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
        start.Environment["WEIR_HOME"] = workDirectory;
        using var process = Process.Start(start)!;
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync().WaitAsync(TimeSpan.FromMinutes(2));
        var output = await stdout;
        Assert.True(process.ExitCode == 0, $"python driver failed ({process.ExitCode}): {await stderr}");
        using var document = JsonDocument.Parse(output.Trim().Split('\n')[^1]);
        var weirFile = document.RootElement.GetProperty("weir_file").GetString()!;
        // The import must come from this checkout's backend, not an installed copy.
        Assert.StartsWith(Path.GetFullPath(SourceRoot!), Path.GetFullPath(weirFile), StringComparison.OrdinalIgnoreCase);
        return [.. document.RootElement.GetProperty("results").EnumerateArray().Select(element => element.Clone())];
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
