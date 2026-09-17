using System.Text.RegularExpressions;

namespace Weir.Core.Jobs;

/// <summary>The broad cause of a failure (<c>FailureKind</c>).</summary>
public enum FailureKind
{
    Auth,
    Credential,
    Network,
    Filesystem,
    RateLimit,
    Validation,
    NotFound,
    Internal,
}

/// <summary>
/// An exception as Python's failure wording sees it: a type name and a message. .NET exceptions
/// report their own type name; the worker's own refusals use Python's names so the stored
/// <c>last_error</c> reads the same on either backend.
/// </summary>
public sealed record FailureCause(string TypeName, string Message, FailureCategory Category)
{
    /// <summary>A <c>RuntimeError(message)</c>, which the Python worker raises for refusals.</summary>
    public static FailureCause RuntimeError(string message) => new("RuntimeError", message, FailureCategory.Other);

    public static FailureCause FromException(Exception exception)
    {
        ArgumentNullException.ThrowIfNull(exception);
        var category = exception switch
        {
            FileNotFoundException or DirectoryNotFoundException or UnauthorizedAccessException => FailureCategory.Filesystem,
            TimeoutException or IOException or System.Net.Sockets.SocketException or System.Net.Http.HttpRequestException => FailureCategory.OsOrNetwork,
            ArgumentException or FormatException or InvalidCastException => FailureCategory.ValueOrType,
            _ => FailureCategory.Other,
        };
        var typeName = exception is AlreadyRecordedFailureException ? AlreadyRecordedFailureException.PythonTypeName : exception.GetType().Name;
        return new FailureCause(typeName, exception.Message, category);
    }
}

/// <summary>
/// The Python exception classes <c>classify_exception</c> tests with <c>isinstance</c>, mapped onto
/// their closest .NET equivalents.
/// </summary>
public enum FailureCategory
{
    /// <summary><c>FileNotFoundError</c>, <c>PermissionError</c> and the other local file errors.</summary>
    Filesystem,

    /// <summary><c>ConnectionError</c>, <c>TimeoutError</c> and other <c>OSError</c>s.</summary>
    OsOrNetwork,

    /// <summary><c>ValueError</c> and <c>TypeError</c>.</summary>
    ValueOrType,

    Other,
}

/// <summary>Port of <c>weir.platform.observability.failure_messages.OperatorFailure</c>.</summary>
public sealed record OperatorFailure(
    string Module,
    string Action,
    FailureKind Kind,
    bool Recoverable,
    string Message,
    string Why,
    string WhatHappensNext,
    string? NextAction,
    string? TechnicalDetail);

/// <summary>Port of <c>operator_failure_from_exception</c> and <c>classify_exception</c>.</summary>
public static partial class OperatorFailures
{
    private static readonly string[] SecretFieldFragments = ["api_key", "apikey", "authorization", "cookie", "password", "secret", "token"];

    private static readonly Dictionary<string, string> ProviderLabels = new(StringComparer.Ordinal)
    {
        ["emby"] = "Emby",
        ["jellyfin"] = "Jellyfin",
        ["plex"] = "Plex",
        ["radarr"] = "Radarr",
        ["sonarr"] = "Sonarr",
    };

    public static FailureKind Classify(FailureCause cause)
    {
        ArgumentNullException.ThrowIfNull(cause);
        var text = $"{cause.TypeName}: {cause.Message}".ToLowerInvariant();
        if (text.Contains("rate limit", StringComparison.Ordinal) || text.Contains("ratelimit", StringComparison.Ordinal) ||
            text.Contains("rate-limit", StringComparison.Ordinal) || text.Contains("429", StringComparison.Ordinal))
        {
            return FailureKind.RateLimit;
        }

        if (text.Contains("credential", StringComparison.Ordinal) || text.Contains("api key", StringComparison.Ordinal) ||
            text.Contains("token", StringComparison.Ordinal) || text.Contains("secret", StringComparison.Ordinal))
        {
            return FailureKind.Credential;
        }

        if (text.Contains("unauthorized", StringComparison.Ordinal) || text.Contains("forbidden", StringComparison.Ordinal) ||
            text.Contains("401", StringComparison.Ordinal) || text.Contains("403", StringComparison.Ordinal))
        {
            return FailureKind.Auth;
        }

        if (cause.Category == FailureCategory.Filesystem)
        {
            return FailureKind.Filesystem;
        }

        if (text.Contains("not found", StringComparison.Ordinal) || text.Contains("404", StringComparison.Ordinal))
        {
            return FailureKind.NotFound;
        }

        return cause.Category switch
        {
            FailureCategory.OsOrNetwork => FailureKind.Network,
            FailureCategory.ValueOrType => FailureKind.Validation,
            _ => FailureKind.Internal,
        };
    }

    public static OperatorFailure FromCause(
        string module,
        string action,
        FailureCause cause,
        string? provider = null,
        bool recoverable = false,
        string? continuation = null)
    {
        ArgumentNullException.ThrowIfNull(cause);
        var kind = Classify(cause);
        var providerLabel = ProviderLabel(provider);
        var where = providerLabel is null ? string.Empty : $" for {providerLabel}";
        var state = recoverable ? "skipped and continued" : "failed";
        var happensNext = string.IsNullOrEmpty(continuation)
            ? recoverable
                ? "Weir will continue with the next available provider."
                : "This job is marked failed so it does not look successful."
            : continuation;
        var why = WhyForKind(kind, provider);
        var message = $"{module} {action}{where} {state}: {why} {happensNext}";
        var detail = SanitizeDiagnosticValue("technical_detail", $"{cause.TypeName}: {cause.Message}");
        return new OperatorFailure(
            module,
            action,
            kind,
            recoverable,
            message,
            why,
            happensNext,
            NextActionForKind(kind, provider, recoverable),
            PythonSlice(detail, 1000));
    }

    /// <summary><c>sanitize_diagnostic_value</c> for a string value.</summary>
    public static string SanitizeDiagnosticValue(string key, string value)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(value);
        var lowered = key.ToLowerInvariant();
        if (SecretFieldFragments.Any(fragment => lowered.Contains(fragment, StringComparison.Ordinal)))
        {
            return "[redacted]";
        }

        return SecretAssignment().Replace(value, match => match.Groups[1].Value + "[redacted]");
    }

    /// <summary>Python's <c>text[:limit]</c>, counted in code points rather than UTF-16 units.</summary>
    public static string PythonSlice(string value, int limit)
    {
        ArgumentNullException.ThrowIfNull(value);
        if (value.Length <= limit)
        {
            return value;
        }

        var count = 0;
        var index = 0;
        while (index < value.Length && count < limit)
        {
            index += char.IsSurrogatePair(value, index) ? 2 : 1;
            count++;
        }

        return value[..index];
    }

    private static string? ProviderLabel(string? provider)
    {
        if (string.IsNullOrEmpty(provider))
        {
            return null;
        }

        var value = provider.Trim();
        return ProviderLabels.TryGetValue(value.ToLowerInvariant(), out var label) ? label : value;
    }

    private static string WhyForKind(FailureKind kind, string? provider)
    {
        var label = ProviderLabel(provider);
        var where = string.IsNullOrEmpty(provider) ? string.Empty : $" from {label}";
        return kind switch
        {
            FailureKind.RateLimit => $"The provider{where} temporarily limited requests.",
            FailureKind.Credential => $"Weir could not use the saved credentials{where}.",
            FailureKind.Auth => $"The service{where} rejected the credentials or permission level.",
            FailureKind.Network => $"Weir could not reach the service{where} over the network.",
            FailureKind.Filesystem => "Weir could not use a file or folder it needed.",
            FailureKind.Validation => "The saved settings or job payload did not pass validation.",
            FailureKind.NotFound => $"The item or endpoint{where} was not found.",
            _ => "The job hit an unexpected error.",
        };
    }

    private static string? NextActionForKind(FailureKind kind, string? provider, bool recoverable)
    {
        var label = ProviderLabel(provider);
        var providerText = string.IsNullOrEmpty(label) ? "the provider" : label;
        return kind switch
        {
            FailureKind.Credential or FailureKind.Auth => $"Re-enter the {providerText} credentials and run the connection test again.",
            FailureKind.Network => $"Check the {providerText} address, network access, and that the service is running.",
            FailureKind.RateLimit => "Wait for the provider limit to reset, or reduce how often this workflow runs.",
            FailureKind.Filesystem => "Check that the file or folder still exists and that Weir can read and write it.",
            FailureKind.Validation => "Review the saved settings for this workflow and save them again.",
            FailureKind.NotFound when !recoverable => "Refresh the source library and run the workflow again.",
            _ => null,
        };
    }

    [GeneratedRegex(@"(\b(?:api[_-]?key|authorization|cookie|password|secret|token)\b\s*[:=]\s*)[^,\s;]+", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex SecretAssignment();
}
