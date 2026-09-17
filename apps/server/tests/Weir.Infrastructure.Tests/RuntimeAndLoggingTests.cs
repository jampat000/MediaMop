using Microsoft.Extensions.Logging;
using Weir.Core.Configuration;
using Weir.Infrastructure.Logging;
using Weir.Infrastructure.Runtime;

namespace Weir.Infrastructure.Tests;

public sealed class RuntimeAndLoggingTests
{
    [Fact]
    public void Runtime_directories_are_created()
    {
        using var temp = new TempDirectory();
        var options = WeirOptionsLoader.Load(new RuntimeEnvironment(
            new Dictionary<string, string> { ["WEIR_HOME"] = temp.Join("home") },
            OperatingSystem.IsWindows(),
            temp.Path,
            temp.Path));

        RuntimeDirectories.Ensure(options);
        RuntimeDirectories.AssertSqliteDbLocationUsable(options.DbPath);

        Assert.True(Directory.Exists(temp.Join("home", "backups")));
        Assert.True(Directory.Exists(temp.Join("home", "logs")));
        Assert.True(Directory.Exists(temp.Join("home", "temp")));
        Assert.True(Directory.Exists(temp.Join("home", "data")));
        Assert.Empty(Directory.GetFiles(temp.Join("home", "data")));
    }

    [Fact]
    public void A_directory_at_the_database_path_is_refused_with_the_python_message()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("weir.sqlite3");
        Directory.CreateDirectory(path);

        var error = Assert.Throws<WeirConfigurationException>(() => RuntimeDirectories.AssertSqliteDbLocationUsable(path));

        Assert.Equal(
            $"SQLite database path must be a file, not a directory: {Path.GetFullPath(path)}. Fix WEIR_DB_PATH or remove the directory at that location.",
            error.Message);
    }

    [Fact]
    public void A_missing_parent_directory_is_refused_with_the_python_message()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("missing", "weir.sqlite3");

        var error = Assert.Throws<WeirConfigurationException>(() => RuntimeDirectories.AssertSqliteDbLocationUsable(path));

        Assert.Equal($"Cannot create files under database directory (check permissions and disk): {temp.Join("missing")}", error.Message);
    }

    [Fact]
    public void An_existing_writable_database_file_passes()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("weir.sqlite3");
        File.WriteAllBytes(path, []);
        RuntimeDirectories.AssertSqliteDbLocationUsable(path);
    }

    [Theory]
    [InlineData("debug", LogLevel.Debug)]
    [InlineData("INFO", LogLevel.Information)]
    [InlineData("warning", LogLevel.Warning)]
    [InlineData("WARN", LogLevel.Warning)]
    [InlineData("error", LogLevel.Error)]
    [InlineData("critical", LogLevel.Critical)]
    [InlineData("fatal", LogLevel.Critical)]
    [InlineData("notset", LogLevel.Trace)]
    [InlineData("verbose", LogLevel.Information)]
    public void Log_level_names_follow_python_logging(string name, LogLevel expected) =>
        Assert.Equal(expected, PythonLogFormat.ParseMinimumLevel(name));

    [Fact]
    public void Json_lines_match_the_python_formatter()
    {
        var at = new DateTimeOffset(2026, 9, 17, 1, 2, 3, TimeSpan.Zero).AddTicks(1234560);
        Assert.Equal(
            "{\"timestamp\": \"2026-09-17T01:02:03.123456Z\", \"level\": \"WARNING\", \"logger\": \"Weir.Test\", " +
            "\"message\": \"caf\\u00e9 \\\"quoted\\\"\\nnext \\ud83d\\ude00\", \"source\": null, \"detail\": null, " +
            "\"correlation_id\": \"abc\", \"job_id\": null}",
            PythonLogFormat.JsonLine(at, LogLevel.Warning, "Weir.Test", "café \"quoted\"\nnext 😀", null, "abc", null));

        var whole = new DateTimeOffset(2026, 9, 17, 1, 2, 3, TimeSpan.Zero);
        var withError = PythonLogFormat.JsonLine(whole, LogLevel.Error, "L", "m", new InvalidOperationException("boom"), null, "7");
        Assert.StartsWith("{\"timestamp\": \"2026-09-17T01:02:03Z\", \"level\": \"ERROR\"", withError, StringComparison.Ordinal);
        Assert.Contains("\"job_id\": \"7\", \"traceback\": \"System.InvalidOperationException: boom\"}", withError, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(LogLevel.Trace, "DEBUG")]
    [InlineData(LogLevel.Debug, "DEBUG")]
    [InlineData(LogLevel.Information, "INFO")]
    [InlineData(LogLevel.Warning, "WARNING")]
    [InlineData(LogLevel.Error, "ERROR")]
    [InlineData(LogLevel.Critical, "CRITICAL")]
    public void Level_names(LogLevel level, string expected) => Assert.Equal(expected, PythonLogFormat.LevelName(level));

    [Fact]
    public void The_file_logger_writes_weir_log_with_the_request_id()
    {
        using var temp = new TempDirectory();
        using (var file = new WeirLogFile(temp.Join("logs", "weir.log"), TimeProvider.System))
        using (var provider = new WeirLogFileLoggerProvider(file, TimeProvider.System, LogLevel.Information))
        {
            var logger = provider.CreateLogger("Weir.Test");
            logger.LogDebug("hidden");
            using (LogContext.BeginRequest("req-1"))
            using (LogContext.BeginJob("42"))
            {
                logger.LogInformation("hello {Name}", "world");
            }

            logger.LogWarning("after");
        }

        var lines = File.ReadAllLines(temp.Join("logs", "weir.log"));
        Assert.Equal(2, lines.Length);
        Assert.Contains("\"message\": \"hello world\"", lines[0], StringComparison.Ordinal);
        Assert.Contains("\"correlation_id\": \"req-1\", \"job_id\": \"42\"", lines[0], StringComparison.Ordinal);
        Assert.Contains("\"correlation_id\": null, \"job_id\": null", lines[1], StringComparison.Ordinal);
    }

    [Fact]
    public void Prune_keeps_recent_lines_and_drops_old_or_unreadable_ones_then_keeps_writing()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("weir.log");
        var now = DateTimeOffset.UtcNow;
        using var file = new WeirLogFile(path, TimeProvider.System);
        file.WriteLine(PythonLogFormat.JsonLine(now.AddDays(-10), LogLevel.Information, "L", "old", null, null, null));
        file.WriteLine("not json");
        file.WriteLine("{\"timestamp\": 5}");
        file.WriteLine(PythonLogFormat.JsonLine(now.AddDays(-1), LogLevel.Information, "L", "recent", null, null, null));

        Assert.True(file.Prune(keepDays: 3));
        file.WriteLine(PythonLogFormat.JsonLine(now, LogLevel.Information, "L", "new", null, null, null));

        var lines = ReadShared(path);
        Assert.Equal(2, lines.Length);
        Assert.Contains("\"recent\"", lines[0], StringComparison.Ordinal);
        Assert.Contains("\"new\"", lines[1], StringComparison.Ordinal);
    }

    [Fact]
    public void Prune_keeps_at_least_one_day()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("weir.log");
        using var file = new WeirLogFile(path, TimeProvider.System);
        file.WriteLine(PythonLogFormat.JsonLine(DateTimeOffset.UtcNow.AddHours(-12), LogLevel.Information, "L", "half a day", null, null, null));
        Assert.True(file.Prune(keepDays: 0));
        Assert.Single(ReadShared(path));
    }

    /// <summary>Read the log while the writer still holds it, as the Logs screen does.</summary>
    private static string[] ReadShared(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd().Split('\n', StringSplitOptions.RemoveEmptyEntries);
    }
}
