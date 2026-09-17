using System.Text.RegularExpressions;
using Weir.Core.Json;

namespace Weir.Core.Observability;

/// <summary>Shared diagnostics vocabulary (port of <c>weir.platform.observability.diagnostics</c>).</summary>
public static partial class Diagnostics
{
    public static readonly IReadOnlyList<string> SecretFieldFragments = ["api_key", "apikey", "authorization", "cookie", "password", "secret", "token"];

    /// <summary><c>sanitize_diagnostic_value</c> for text values.</summary>
    public static string SanitizeText(string key, string value)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(value);
        if (SecretFieldFragments.Any(fragment => key.Contains(fragment, StringComparison.OrdinalIgnoreCase)))
        {
            return "[redacted]";
        }

        return SecretAssignment().Replace(value, match => match.Groups[1].Value + "[redacted]");
    }

    /// <summary><c>severity_for_result</c>.</summary>
    public static string SeverityForResult(string result) => (result ?? string.Empty).ToLowerInvariant() switch
    {
        "failed" => "error",
        "warning" or "retrying" => "warning",
        _ => "info",
    };

    [GeneratedRegex(@"(\b(?:api[_-]?key|authorization|cookie|password|secret|token)\b\s*[:=]\s*)[^,\s;]+", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex SecretAssignment();
}

/// <summary>One diagnostics event in the shared vocabulary (port of <c>DiagnosticEvent</c>).</summary>
public sealed record DiagnosticEvent(
    string Module,
    string Action,
    string Trigger,
    string Result,
    string Severity,
    string? Provider = null,
    string? MediaScope = null,
    string? CorrelationId = null,
    string? Reason = null,
    string? NextAction = null,
    IReadOnlyList<KeyValuePair<string, long>>? Counts = null)
{
    /// <summary><c>as_safe_dict</c>: optional fields only when set, secret-looking values redacted.</summary>
    public PyDict AsSafeDict()
    {
        var payload = new PyDict()
            .Set("module", Module)
            .Set("action", Action)
            .Set("trigger", Trigger)
            .Set("result", Result)
            .Set("severity", Severity);
        foreach (var (key, value) in new[]
        {
            ("provider", Provider), ("media_scope", MediaScope), ("correlation_id", CorrelationId),
            ("reason", Reason), ("next_action", NextAction),
        })
        {
            if (!string.IsNullOrEmpty(value))
            {
                payload.Set(key, Diagnostics.SanitizeText(key, value));
            }
        }

        if (Counts is { Count: > 0 })
        {
            var counts = new PyDict();
            foreach (var (key, value) in Counts)
            {
                counts.Set(key, value);
            }

            payload.Set("counts", counts);
        }

        return payload;
    }
}

/// <summary>Plain-language operator labels (port of <c>weir.platform.observability.operator_messages</c>).</summary>
public static class OperatorMessages
{
    private static readonly Dictionary<string, string> ProviderLabels = new(StringComparer.Ordinal)
    {
        ["emby"] = "Emby", ["jellyfin"] = "Jellyfin", ["plex"] = "Plex", ["radarr"] = "Radarr", ["sonarr"] = "Sonarr",
    };

    private static readonly Dictionary<string, string> ScopeLabels = new(StringComparer.Ordinal)
    {
        ["movie"] = "Movies", ["movies"] = "Movies", ["tv"] = "TV episodes", ["episode"] = "TV episodes",
    };

    public static string? ProviderLabel(string? provider)
    {
        if (string.IsNullOrEmpty(provider))
        {
            return null;
        }

        var value = provider.Trim();
        return ProviderLabels.TryGetValue(value.ToLowerInvariant(), out var label) ? label : value;
    }

    public static string? MediaScopeLabel(string? mediaScope)
    {
        if (string.IsNullOrEmpty(mediaScope))
        {
            return null;
        }

        var value = mediaScope.Trim();
        return ScopeLabels.TryGetValue(value.ToLowerInvariant(), out var label) ? label : value;
    }

    /// <summary><c>count_summary</c>: numeric counts only (booleans and nulls dropped), never negative.</summary>
    public static PyDict CountSummary(IReadOnlyList<KeyValuePair<string, long?>> counts)
    {
        ArgumentNullException.ThrowIfNull(counts);
        var summary = new PyDict();
        foreach (var (key, value) in counts)
        {
            if (value is { } v)
            {
                summary.Set(key, Math.Max(0, v));
            }
        }

        return summary;
    }

    /// <summary><c>activity_detail_envelope</c>.</summary>
    public static PyDict ActivityDetailEnvelope(
        string module,
        string action,
        string trigger,
        string result,
        string? provider = null,
        string? mediaScope = null,
        IReadOnlyList<KeyValuePair<string, long?>>? counts = null,
        string? userMessage = null,
        string? nextAction = null)
    {
        var payload = new PyDict()
            .Set("module", module)
            .Set("action", action)
            .Set("trigger", trigger)
            .Set("result", result)
            .Set("severity", Diagnostics.SeverityForResult(result));
        if (ProviderLabel(provider) is { } providerLabel)
        {
            payload.Set("provider", providerLabel);
        }

        if (MediaScopeLabel(mediaScope) is { } scopeLabel)
        {
            payload.Set("media_scope_label", scopeLabel);
        }

        if (!string.IsNullOrEmpty(mediaScope))
        {
            payload.Set("media_scope", mediaScope);
        }

        if (counts is { Count: > 0 })
        {
            payload.Set("counts", CountSummary(counts));
        }

        if (!string.IsNullOrEmpty(userMessage))
        {
            payload.Set("user_message", userMessage);
        }

        if (!string.IsNullOrEmpty(nextAction))
        {
            payload.Set("next_action", nextAction);
        }

        return payload;
    }
}

/// <summary>The failure kinds operators see (port of <c>FailureKind</c>).</summary>
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

/// <summary>What happened to an exception, in the terms <c>classify_exception</c> uses.</summary>
/// <param name="TypeName">Python's exception class name (<c>type(exc).__name__</c>).</param>
/// <param name="Message"><c>str(exc)</c>.</param>
/// <param name="Category">Which Python exception family it belongs to.</param>
public sealed record FailureSubject(string TypeName, string Message, ExceptionCategory Category);

/// <summary>The Python exception families <c>classify_exception</c> checks with <c>isinstance</c>.</summary>
public enum ExceptionCategory
{
    Other,

    /// <summary>FileNotFoundError, FileExistsError, IsADirectoryError, NotADirectoryError, PermissionError.</summary>
    Filesystem,

    /// <summary>ConnectionError, TimeoutError, socket.timeout, or any other OSError.</summary>
    NetworkOrOs,

    /// <summary>ValueError or TypeError.</summary>
    Validation,
}

/// <summary>An operator-facing failure (port of <c>OperatorFailure</c>).</summary>
public sealed record OperatorFailure(
    string Module,
    string Action,
    FailureKind Kind,
    bool Recoverable,
    string Message,
    string Why,
    string WhatHappensNext,
    string? NextAction,
    string? TechnicalDetail)
{
    public PyDict AsDict()
    {
        var output = new PyDict()
            .Set("failure_kind", FailureMessages.KindText(Kind))
            .Set("recoverable", Recoverable)
            .Set("what_failed", $"{Module} {Action}")
            .Set("why", Why)
            .Set("what_happens_next", WhatHappensNext)
            .Set("user_message", Message);
        if (!string.IsNullOrEmpty(NextAction))
        {
            output.Set("next_action", NextAction);
        }

        if (!string.IsNullOrEmpty(TechnicalDetail))
        {
            output.Set("technical_detail", TechnicalDetail);
        }

        return output;
    }
}

/// <summary>Port of <c>weir.platform.observability.failure_messages</c>.</summary>
public static class FailureMessages
{
    public static string KindText(FailureKind kind) => kind switch
    {
        FailureKind.Auth => "auth",
        FailureKind.Credential => "credential",
        FailureKind.Network => "network",
        FailureKind.Filesystem => "filesystem",
        FailureKind.RateLimit => "rate_limit",
        FailureKind.Validation => "validation",
        FailureKind.NotFound => "not_found",
        _ => "internal",
    };

    /// <summary><c>classify_exception</c>.</summary>
    public static FailureKind Classify(FailureSubject exception)
    {
        ArgumentNullException.ThrowIfNull(exception);
        var text = $"{exception.TypeName}: {exception.Message}".ToLowerInvariant();
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

        if (exception.Category == ExceptionCategory.Filesystem)
        {
            return FailureKind.Filesystem;
        }

        if (text.Contains("not found", StringComparison.Ordinal) || text.Contains("404", StringComparison.Ordinal))
        {
            return FailureKind.NotFound;
        }

        return exception.Category switch
        {
            ExceptionCategory.NetworkOrOs => FailureKind.Network,
            ExceptionCategory.Validation => FailureKind.Validation,
            _ => FailureKind.Internal,
        };
    }

    public static string WhyForKind(FailureKind kind, string? provider)
    {
        var where = OperatorMessages.ProviderLabel(provider) is { } label ? $" from {label}" : string.Empty;
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

    public static string? NextActionForKind(FailureKind kind, string? provider, bool recoverable)
    {
        var providerText = OperatorMessages.ProviderLabel(provider) ?? "the provider";
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

    /// <summary><c>operator_failure_from_exception</c>.</summary>
    public static OperatorFailure FromException(
        string module,
        string action,
        FailureSubject exception,
        string? provider = null,
        bool recoverable = false,
        string? continuation = null)
    {
        ArgumentNullException.ThrowIfNull(exception);
        var kind = Classify(exception);
        var providerText = OperatorMessages.ProviderLabel(provider);
        var where = providerText is not null ? $" for {providerText}" : string.Empty;
        var state = recoverable ? "skipped and continued" : "failed";
        var happensNext = !string.IsNullOrEmpty(continuation)
            ? continuation
            : recoverable
                ? "Weir will continue with the next available provider."
                : "This job is marked failed so it does not look successful.";
        var message = $"{module} {action}{where} {state}: {WhyForKind(kind, provider)} {happensNext}";
        var detail = Diagnostics.SanitizeText("technical_detail", $"{exception.TypeName}: {exception.Message}");
        return new OperatorFailure(
            module, action, kind, recoverable, message, WhyForKind(kind, provider), happensNext,
            NextActionForKind(kind, provider, recoverable),
            Auth.SessionRules.Truncate(detail, 1000));
    }

    /// <summary>The Python exception a .NET exception stands for.</summary>
    public static FailureSubject FromDotNet(Exception exception)
    {
        ArgumentNullException.ThrowIfNull(exception);
        return exception switch
        {
            FileNotFoundException or DirectoryNotFoundException => new FailureSubject("FileNotFoundError", exception.Message, ExceptionCategory.Filesystem),
            UnauthorizedAccessException => new FailureSubject("PermissionError", exception.Message, ExceptionCategory.Filesystem),
            TimeoutException => new FailureSubject("TimeoutError", exception.Message, ExceptionCategory.NetworkOrOs),
            System.Net.Http.HttpRequestException or System.Net.Sockets.SocketException => new FailureSubject("ConnectionError", exception.Message, ExceptionCategory.NetworkOrOs),
            IOException => new FailureSubject("OSError", exception.Message, ExceptionCategory.NetworkOrOs),
            ArgumentException or FormatException or InvalidCastException or PyValueErrorException or PyTypeErrorException =>
                new FailureSubject("ValueError", exception.Message, ExceptionCategory.Validation),
            _ => new FailureSubject(exception.GetType().Name, exception.Message, ExceptionCategory.Other),
        };
    }
}

/// <summary>Port of <c>weir.platform.observability.metrics_truth</c>.</summary>
public static class MetricsTruth
{
    public static void RequireNonNegative(IReadOnlyDictionary<string, long> counts)
    {
        ArgumentNullException.ThrowIfNull(counts);
        foreach (var (name, value) in counts)
        {
            if (value < 0)
            {
                throw new PyValueErrorException($"Metric {PyConvert.ReprString(name)} must not be negative.");
            }
        }
    }

    public static long FinalizedSuccessTotal(IReadOnlyDictionary<string, long> counts)
    {
        RequireNonNegative(counts);
        return counts.Values.Sum();
    }
}
