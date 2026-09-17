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

/// <summary>A fact that runs only where the Python backend's virtualenv exists (cross-checks against the reference).</summary>
[AttributeUsage(AttributeTargets.Method)]
internal sealed class PythonFactAttribute : FactAttribute
{
    public PythonFactAttribute()
    {
        if (PythonBackend.Interpreter is null)
        {
            Skip = "apps/backend/.venv is not present; the Python cross-check needs it.";
        }
    }
}

/// <summary>Runs snippets with the Python backend's interpreter and <c>apps/backend/src</c> on the path.</summary>
internal static class PythonBackend
{
    public static string? Interpreter
    {
        get
        {
            var root = RepositoryPaths.RepositoryRoot;
            if (root is null)
            {
                return null;
            }

            var windows = System.IO.Path.Join(root, "apps", "backend", ".venv", "Scripts", "python.exe");
            var unix = System.IO.Path.Join(root, "apps", "backend", ".venv", "bin", "python");
            return File.Exists(windows) ? windows : File.Exists(unix) ? unix : null;
        }
    }

    /// <summary>Run <paramref name="code"/>; returns stdout. Fails the test with stderr on a non-zero exit.</summary>
    public static string Run(string code, IReadOnlyDictionary<string, string> environment)
    {
        var root = RepositoryPaths.RepositoryRoot!;
        var start = new System.Diagnostics.ProcessStartInfo(Interpreter!)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            UseShellExecute = false,
            WorkingDirectory = System.IO.Path.Join(root, "apps", "backend"),
        };
        start.ArgumentList.Add("-");
        foreach (var key in start.Environment.Keys.Where(k => k.StartsWith("WEIR_", StringComparison.OrdinalIgnoreCase)).ToList())
        {
            start.Environment.Remove(key);
        }

        start.Environment["PYTHONPATH"] = System.IO.Path.Join(root, "apps", "backend", "src");
        start.Environment["PYTHONIOENCODING"] = "utf-8";
        foreach (var (key, value) in environment)
        {
            start.Environment[key] = value;
        }

        using var process = System.Diagnostics.Process.Start(start)!;
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
