using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Logging.Console;

namespace Weir.Infrastructure.Logging;

/// <summary>Console lines in the Python backend's format (<see cref="PythonLogFormat.ConsoleLine"/>).</summary>
public sealed class WeirConsoleFormatter : ConsoleFormatter
{
    public const string FormatterName = "weir";

    private readonly TimeProvider _time;

    public WeirConsoleFormatter(TimeProvider time)
        : base(FormatterName)
    {
        _time = time;
    }

    public override void Write<TState>(in LogEntry<TState> logEntry, IExternalScopeProvider? scopeProvider, TextWriter textWriter)
    {
        ArgumentNullException.ThrowIfNull(textWriter);
        var message = logEntry.Formatter(logEntry.State, logEntry.Exception);
        textWriter.WriteLine(PythonLogFormat.ConsoleLine(_time.GetUtcNow(), logEntry.LogLevel, logEntry.Category, message, logEntry.Exception));
    }
}
