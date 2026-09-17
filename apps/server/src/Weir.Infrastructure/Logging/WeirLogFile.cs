using System.Globalization;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace Weir.Infrastructure.Logging;

/// <summary>
/// The single JSON-lines runtime log, <c>{WEIR_LOG_DIR}/weir.log</c>. Writes and the retention
/// rewrite share one lock so the file is never replaced while a handle is open, which Windows
/// does not allow (port of <c>LockedFileHandler</c> and <c>prune_active_log_file</c>).
/// </summary>
public sealed class WeirLogFile : IDisposable
{
    private readonly Lock _lock = new();
    private readonly TimeProvider _time;
    private FileStream? _stream;
    private bool _disposed;

    public WeirLogFile(string path, TimeProvider time)
    {
        ArgumentException.ThrowIfNullOrEmpty(path);
        Path = System.IO.Path.GetFullPath(path);
        _time = time;
        var directory = System.IO.Path.GetDirectoryName(Path);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        _stream = OpenForAppend(Path);
    }

    public string Path { get; }

    public void WriteLine(string line)
    {
        ArgumentNullException.ThrowIfNull(line);
        var bytes = Encoding.UTF8.GetBytes(line + "\n");
        lock (_lock)
        {
            if (_stream is null)
            {
                return;
            }

            _stream.Write(bytes);
            _stream.Flush();
        }
    }

    /// <summary>
    /// Keep only lines whose <c>timestamp</c> is within <paramref name="keepDays"/> (at least one day).
    /// Lines that are not JSON with a readable timestamp are dropped, as in Python. Returns
    /// <see langword="false"/> when the file could not be rewritten; the log is left as it was.
    /// </summary>
    public bool Prune(int keepDays)
    {
        var cutoff = _time.GetUtcNow() - TimeSpan.FromDays(Math.Max(1, keepDays));
        lock (_lock)
        {
            _stream?.Dispose();
            _stream = null;
            string? temporary = null;
            try
            {
                if (!File.Exists(Path))
                {
                    return true;
                }

                temporary = System.IO.Path.Join(
                    System.IO.Path.GetDirectoryName(Path),
                    $".{System.IO.Path.GetFileName(Path)}.{Guid.NewGuid():N}.prune");
                using (var reader = new StreamReader(Path, Encoding.UTF8))
                using (var writer = new StreamWriter(temporary, append: false, new UTF8Encoding(false)))
                {
                    writer.NewLine = "\n";
                    while (reader.ReadLine() is { } raw)
                    {
                        if (TryReadTimestamp(raw, out var at) && at >= cutoff)
                        {
                            writer.WriteLine(raw.TrimEnd('\n'));
                        }
                    }
                }

                File.Move(temporary, Path, overwrite: true);
                temporary = null;
                return true;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                if (temporary is not null)
                {
                    try
                    {
                        File.Delete(temporary);
                    }
                    catch (Exception cleanup) when (cleanup is IOException or UnauthorizedAccessException)
                    {
                        // Best effort, as in Python.
                    }
                }

                return false;
            }
            finally
            {
                if (!_disposed)
                {
                    _stream = OpenForAppend(Path);
                }
            }
        }
    }

    public void Dispose()
    {
        lock (_lock)
        {
            _disposed = true;
            _stream?.Dispose();
            _stream = null;
        }
    }

    internal static bool TryReadTimestamp(string raw, out DateTimeOffset timestamp)
    {
        timestamp = default;
        try
        {
            using var document = JsonDocument.Parse(raw);
            if (document.RootElement.ValueKind != JsonValueKind.Object ||
                !document.RootElement.TryGetProperty("timestamp", out var value) ||
                value.ValueKind != JsonValueKind.String)
            {
                return false;
            }

            var text = value.GetString()!;
            return DateTimeOffset.TryParse(
                text.EndsWith('Z') ? text[..^1] + "+00:00" : text,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out timestamp);
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static FileStream OpenForAppend(string path) =>
        new(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete);
}

/// <summary>Writes every log entry at or above the configured level to <see cref="WeirLogFile"/>.</summary>
public sealed class WeirLogFileLoggerProvider : ILoggerProvider
{
    private readonly WeirLogFile _file;
    private readonly TimeProvider _time;
    private readonly LogLevel _minimumLevel;

    public WeirLogFileLoggerProvider(WeirLogFile file, TimeProvider time, LogLevel minimumLevel)
    {
        _file = file;
        _time = time;
        _minimumLevel = minimumLevel;
    }

    public ILogger CreateLogger(string categoryName) => new FileLogger(this, categoryName);

    public void Dispose()
    {
        // The file is owned by whoever created it.
    }

    private sealed class FileLogger(WeirLogFileLoggerProvider provider, string category) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => logLevel != LogLevel.None && logLevel >= provider._minimumLevel;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            ArgumentNullException.ThrowIfNull(formatter);
            if (!IsEnabled(logLevel))
            {
                return;
            }

            provider._file.WriteLine(PythonLogFormat.JsonLine(
                provider._time.GetUtcNow(),
                logLevel,
                category,
                formatter(state, exception),
                exception,
                LogContext.RequestId,
                LogContext.JobId));
        }
    }
}
