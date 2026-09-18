using Weir.Core.Json;
using Weir.Core.Time;

namespace Weir.Core.Logs;

/// <summary>One parsed line of <c>weir.log</c> (port of <c>ParsedLogEntry</c>).</summary>
public sealed record ParsedLogEntry(
    string Timestamp,
    string Level,
    string Component,
    string Message,
    string? Detail,
    string? Traceback,
    string? Source,
    string Logger,
    string? CorrelationId,
    string? JobId);

/// <summary>The result of reading the log for the Logs screen.</summary>
public sealed record SuiteLogsResult(IReadOnlyList<ParsedLogEntry> Items, long Total, long Errors, long Warnings, long Information);

/// <summary>Port of <c>weir.platform.suite_settings.logs_service</c> reading and filtering.</summary>
public sealed class SuiteLogFilter
{
    private readonly string? _level;
    private readonly string _search;
    private readonly bool? _hasException;
    private readonly Queue<ParsedLogEntry> _rows = new();
    private readonly int _capacity;
    private long _total;
    private long _errors;
    private long _warnings;
    private long _information;

    public SuiteLogFilter(string? level, string? search, bool? hasException, long limit)
    {
        var requested = (level ?? string.Empty).Trim().ToUpperInvariant();
        _level = requested.Length == 0 ? null : requested;
        _search = (search ?? string.Empty).Trim().ToLowerInvariant();
        _hasException = hasException;
        _capacity = (int)Math.Max(1, Math.Min(limit, 250));
    }

    public static SuiteLogsResult Empty => new([], 0, 0, 0, 0);

    public void Add(string rawLine)
    {
        var entry = Parse(rawLine);
        if (entry is null || SkipLowValueNoise(entry))
        {
            return;
        }

        _total++;
        switch (entry.Level)
        {
            case "ERROR" or "CRITICAL":
                _errors++;
                break;
            case "WARNING":
                _warnings++;
                break;
            default:
                _information++;
                break;
        }

        if (_level is not null && entry.Level != _level)
        {
            return;
        }

        if (_hasException == true && string.IsNullOrEmpty(entry.Traceback))
        {
            return;
        }

        if (_hasException == false && !string.IsNullOrEmpty(entry.Traceback))
        {
            return;
        }

        if (_search.Length > 0)
        {
            var haystack = string.Join(
                " ",
                new[]
                {
                    entry.Message, entry.Detail ?? string.Empty, entry.Traceback ?? string.Empty, entry.Logger,
                    entry.Source ?? string.Empty, entry.Component, entry.CorrelationId ?? string.Empty, entry.JobId ?? string.Empty,
                }.Where(part => part.Length > 0)).ToLowerInvariant();
            if (!haystack.Contains(_search, StringComparison.Ordinal))
            {
                return;
            }
        }

        _rows.Enqueue(entry);
        if (_rows.Count > _capacity)
        {
            _rows.Dequeue();
        }
    }

    public SuiteLogsResult Result() => new([.. _rows.Reverse()], _total, _errors, _warnings, _information);

    /// <summary><c>_parse_log_line</c>.</summary>
    public static ParsedLogEntry? Parse(string raw)
    {
        PyJson payload;
        try
        {
            payload = PyJsonParser.Parse(raw);
        }
        catch (PyJsonDecodeException)
        {
            return null;
        }

        if (payload is not PyDict dict)
        {
            return null;
        }

        var timestamp = OrText(dict.Get("timestamp"), string.Empty).Trim();
        var level = OrText(dict.Get("level"), "INFO").Trim().ToUpperInvariant();
        if (level.Length == 0)
        {
            level = "INFO";
        }

        var logger = OrText(dict.Get("logger"), "weir").Trim();
        if (logger.Length == 0)
        {
            logger = "weir";
        }

        var message = OrText(dict.Get("message"), string.Empty).Trim();
        if (timestamp.Length == 0 || message.Length == 0)
        {
            return null;
        }

        var source = dict.Get("source");
        return new ParsedLogEntry(
            timestamp,
            level,
            ComponentLabel(logger, source),
            message,
            CleanOptional(dict.Get("detail")),
            CleanOptional(dict.Get("traceback")),
            CleanOptional(source),
            logger,
            CleanOptional(dict.Get("correlation_id")),
            CleanOptional(dict.Get("job_id")));
    }

    /// <summary>The <c>SuiteLogEntryOut</c> JSON, or <see langword="null"/> when the timestamp does not parse.</summary>
    public static PyDict? ToOut(ParsedLogEntry entry)
    {
        ArgumentNullException.ThrowIfNull(entry);
        if (!PyDateTime.TryFromIsoFormat(entry.Timestamp.Replace("Z", "+00:00", StringComparison.Ordinal), out var parsed))
        {
            return null;
        }

        return new PyDict()
            .Set("timestamp", parsed.PydanticJson())
            .Set("level", entry.Level)
            .Set("component", entry.Component)
            .Set("message", entry.Message)
            .Set("detail", entry.Detail)
            .Set("traceback", entry.Traceback)
            .Set("source", entry.Source)
            .Set("logger", entry.Logger)
            .Set("correlation_id", entry.CorrelationId)
            .Set("job_id", entry.JobId);
    }

    private static string OrText(PyJson? value, string fallback) => value is null || !value.IsTruthy ? fallback : PyConvert.Str(value);

    private static string ComponentLabel(string logger, PyJson? source)
    {
        var sourceText = source is null || !source.IsTruthy ? string.Empty : PyConvert.Str(source);
        var haystack = $"{logger} {sourceText}".ToLowerInvariant();
        if (haystack.Contains("weir.processing", StringComparison.Ordinal))
        {
            return "Processing";
        }

        if (haystack.Contains("platform.auth", StringComparison.Ordinal))
        {
            return "Authentication";
        }

        return haystack.Contains("platform.activity", StringComparison.Ordinal) ? "Activity" : "System";
    }

    private static string? CleanOptional(PyJson? value)
    {
        if (value is null or PyNull)
        {
            return null;
        }

        var text = PyConvert.Str(value).Trim();
        return text.Length == 0 ? null : text;
    }

    private static bool SkipLowValueNoise(ParsedLogEntry entry) =>
        entry.Level is not ("ERROR" or "WARNING" or "CRITICAL") && !entry.Logger.StartsWith("weir", StringComparison.Ordinal);
}
