using System.Globalization;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Net;
using Weir.Core.Time;

namespace Weir.Core.Notifications;

/// <summary>A <c>notification_channels</c> row.</summary>
public sealed record NotificationChannelRecord(
    long Id,
    string Label,
    string Provider,
    string Url,
    string EventsJson,
    bool Enabled,
    PyDateTime CreatedAt,
    PyDateTime UpdatedAt);

/// <summary>Port of <c>weir.platform.notifications.model</c>, <c>ops</c> validation and <c>dispatch</c> payloads.</summary>
public static class NotificationRules
{
    public static readonly IReadOnlyList<string> SupportedEvents = ["job_completed", "job_failed", "refiner_job_completed", "refiner_job_failed"];

    public static readonly IReadOnlyList<string> SupportedProviders = ["webhook", "discord"];

    /// <summary><c>_parse_events</c>: the string items of the stored JSON list; anything unreadable is empty.</summary>
    public static List<string> ParseEvents(string eventsJson)
    {
        try
        {
            return PyJsonParser.Parse(eventsJson ?? string.Empty) switch
            {
                PyList list => [.. list.Items.OfType<PyStr>().Select(item => item.Value)],
                PyDict dict => [.. dict.Keys],
                PyStr text => [.. text.Value.Select(c => c.ToString())],
                _ => [],
            };
        }
        catch (PyJsonDecodeException)
        {
            return [];
        }
    }

    /// <summary><c>json.dumps(events)</c>.</summary>
    public static string SerializeEvents(IEnumerable<string> events) =>
        PyJsonWriter.Dumps(new PyList(events.Select(e => (PyJson)new PyStr(e))), PyJsonFormat.Default);

    /// <summary><c>_validate_channel_input</c>. Throws <see cref="PyValueErrorException"/> with the operator message.</summary>
    public static void Validate(string label, string provider, string url, IReadOnlyList<string> events)
    {
        ArgumentNullException.ThrowIfNull(events);
        if ((label ?? string.Empty).Trim().Length == 0)
        {
            throw new PyValueErrorException("Label must not be empty.");
        }

        if (!SupportedProviders.Contains(provider, StringComparer.Ordinal))
        {
            throw new PyValueErrorException($"Unsupported provider: {PyStrings.Repr(provider ?? string.Empty)}. Choose from: {string.Join(", ", SupportedProviders)}");
        }

        ExternalUrlPolicy.ValidateExternalProviderUrl(url);
        var bad = events.Where(e => !SupportedEvents.Contains(e, StringComparer.Ordinal)).ToList();
        if (bad.Count > 0)
        {
            throw new PyValueErrorException($"Unknown events: {string.Join(", ", bad)}. Supported: {string.Join(", ", SupportedEvents)}");
        }

        if (events.Count == 0)
        {
            throw new PyValueErrorException("At least one event must be selected.");
        }
    }

    public static PyDict ChannelOut(NotificationChannelRecord row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return new PyDict()
            .Set("id", row.Id)
            .Set("label", row.Label)
            .Set("provider", row.Provider)
            .Set("url", row.Url)
            .Set("events", new PyList(ParseEvents(row.EventsJson).Select(e => (PyJson)new PyStr(e))))
            .Set("enabled", row.Enabled)
            .Set("created_at", row.CreatedAt.PydanticJson())
            .Set("updated_at", row.UpdatedAt.PydanticJson());
    }

    public static PyDict ListOut(IEnumerable<NotificationChannelRecord> rows) => new PyDict()
        .Set("items", new PyList(rows.Select(row => (PyJson)ChannelOut(row))))
        .Set("supported_events", new PyList(SupportedEvents.Select(e => (PyJson)new PyStr(e))))
        .Set("supported_providers", new PyList(SupportedProviders.Select(p => (PyJson)new PyStr(p))));

    /// <summary><c>_build_webhook_payload</c>.</summary>
    public static byte[] WebhookPayload(string jobEvent, string module, long jobId, string jobKind, string title, string detail, PyDateTime now) =>
        PyJsonWriter.DumpsUtf8(
            new PyDict()
                .Set("event", jobEvent)
                .Set("module", module)
                .Set("job_id", jobId)
                .Set("job_kind", jobKind)
                .Set("title", title)
                .Set("detail", detail)
                .Set("timestamp", now.IsoFormat())
                .Set("app", "Weir"),
            PyJsonFormat.Default);

    /// <summary><c>_build_discord_payload</c>.</summary>
    public static byte[] DiscordPayload(string title, string detail, string jobEvent, string module, long jobId, PyDateTime now)
    {
        var color = jobEvent.Contains("completed", StringComparison.Ordinal) ? 0x2ECC71 : 0xE74C3C;
        var embed = new PyDict()
            .Set("title", title)
            .Set("description", detail)
            .Set("color", color)
            .Set("fields", new PyList(
            [
                new PyDict().Set("name", "Module").Set("value", module).Set("inline", true),
                new PyDict().Set("name", "Job ID").Set("value", jobId.ToString(CultureInfo.InvariantCulture)).Set("inline", true),
            ]))
            .Set("footer", new PyDict().Set("text", "Weir"))
            .Set("timestamp", now.IsoFormat());
        return PyJsonWriter.DumpsUtf8(new PyDict().Set("embeds", new PyList([embed])), PyJsonFormat.Default);
    }

    /// <summary>
    /// The title and detail <c>dispatch_job_notification</c> sends. <paramref name="willRetry"/> is
    /// meaningless for <c>completed</c> and defaults to <see langword="false"/> for every other caller.
    /// </summary>
    /// <remarks>
    /// #540 item 6: Python always says "exhausted all retry attempts" for a failed event, even for the
    /// attempt that is about to retry (the permanently-failed check in <c>DispatchJobNotification</c>
    /// keeps that wrong wording from actually reaching a channel today, but the text itself was still
    /// wrong on its own terms). This reuses the retry-aware vocabulary <c>WorkerFailures</c> already has
    /// from #488, so the wording is correct independently of that guard.
    /// </remarks>
    /// <summary>
    /// Display names for module keys whose plain capitalization would not read as a person expects. The
    /// "refiner" module key is unchanged (it feeds the stored <c>{module}_job_{eventKind}</c> event name),
    /// but the app that runs it is just called Weir now.
    /// </summary>
    private static readonly Dictionary<string, string> ModuleDisplayNames = new(StringComparer.OrdinalIgnoreCase)
    {
        ["refiner"] = "Weir",
    };

    public static (string Event, string Title, string Detail) JobNotification(string module, string eventKind, long jobId, string jobKind, bool willRetry = false)
    {
        ArgumentNullException.ThrowIfNull(module);
        var capitalized = ModuleDisplayNames.TryGetValue(module, out var displayName)
            ? displayName
            : module.Length == 0 ? module : char.ToUpperInvariant(module[0]) + module[1..].ToLowerInvariant();
        if (eventKind == "completed")
        {
            return ($"{module}_job_{eventKind}", $"{capitalized} job completed", $"Job {jobId} ({jobKind}) finished successfully.");
        }

        var detail = willRetry
            ? $"Job {jobId} ({jobKind}) failed. {WorkerFailures.WillRetryContinuation}"
            : $"Job {jobId} ({jobKind}) exhausted all retry attempts.";
        return ($"{module}_job_{eventKind}", $"{capitalized} job failed", detail);
    }
}

/// <summary>The parts of <c>urllib.parse.urlsplit</c> Weir reads.</summary>
public sealed record SplitUrl(string Scheme, string Netloc, string Path, string Query, string Fragment)
{
    /// <summary><c>.hostname</c>: lower-cased, brackets removed, <see langword="null"/> when empty.</summary>
    public string? Hostname
    {
        get
        {
            var hostinfo = Netloc[(Netloc.LastIndexOf('@') + 1)..];
            string host;
            if (hostinfo.Contains('[', StringComparison.Ordinal))
            {
                var after = hostinfo[(hostinfo.IndexOf('[', StringComparison.Ordinal) + 1)..];
                var close = after.IndexOf(']', StringComparison.Ordinal);
                host = close < 0 ? after : after[..close];
            }
            else
            {
                var colon = hostinfo.IndexOf(':', StringComparison.Ordinal);
                host = colon < 0 ? hostinfo : hostinfo[..colon];
            }

            return host.Length == 0 ? null : host.ToLowerInvariant();
        }
    }

    public bool HasUserInfo => Netloc.Contains('@', StringComparison.Ordinal);

    public string? Username
    {
        get
        {
            var at = Netloc.LastIndexOf('@');
            if (at < 0)
            {
                return null;
            }

            var userinfo = Netloc[..at];
            var colon = userinfo.IndexOf(':', StringComparison.Ordinal);
            return colon < 0 ? userinfo : userinfo[..colon];
        }
    }

    public string? Password
    {
        get
        {
            var at = Netloc.LastIndexOf('@');
            if (at < 0)
            {
                return null;
            }

            var userinfo = Netloc[..at];
            var colon = userinfo.IndexOf(':', StringComparison.Ordinal);
            return colon < 0 ? null : userinfo[(colon + 1)..];
        }
    }

    /// <summary><c>.port</c>. Throws <see cref="PyValueErrorException"/> for a port that is not a number in range.</summary>
    public int? Port
    {
        get
        {
            var hostinfo = Netloc[(Netloc.LastIndexOf('@') + 1)..];
            string port;
            if (hostinfo.Contains('[', StringComparison.Ordinal))
            {
                var tail = hostinfo[(hostinfo.IndexOf(']', StringComparison.Ordinal) + 1)..];
                port = tail.StartsWith(':') ? tail[1..] : string.Empty;
            }
            else
            {
                var colon = hostinfo.IndexOf(':', StringComparison.Ordinal);
                port = colon < 0 ? string.Empty : hostinfo[(colon + 1)..];
            }

            if (port.Length == 0)
            {
                return null;
            }

            if (!port.All(char.IsAsciiDigit) || !int.TryParse(port, NumberStyles.None, CultureInfo.InvariantCulture, out var number))
            {
                throw new PyValueErrorException($"Port could not be cast to integer value as {PyStrings.Repr(port)}");
            }

            if (number > 65535)
            {
                throw new PyValueErrorException("Port out of range 0-65535");
            }

            return number;
        }
    }

    /// <summary>Python 3.11 <c>urlsplit</c>.</summary>
    public static SplitUrl Parse(string raw)
    {
        ArgumentNullException.ThrowIfNull(raw);
        var url = raw.TrimStart(Enumerable.Range(0, 0x21).Select(i => (char)i).ToArray());
        url = url.Replace("\t", string.Empty, StringComparison.Ordinal).Replace("\r", string.Empty, StringComparison.Ordinal).Replace("\n", string.Empty, StringComparison.Ordinal);
        var scheme = string.Empty;
        var netloc = string.Empty;
        var query = string.Empty;
        var fragment = string.Empty;
        var i = url.IndexOf(':', StringComparison.Ordinal);
        if (i > 0 && char.IsAscii(url[0]) && char.IsLetter(url[0]) &&
            url[..i].All(c => char.IsAsciiLetterOrDigit(c) || c is '+' or '-' or '.'))
        {
            scheme = url[..i].ToLowerInvariant();
            url = url[(i + 1)..];
        }

        if (url.StartsWith("//", StringComparison.Ordinal))
        {
            var rest = url[2..];
            var delimiter = rest.IndexOfAny(['/', '?', '#']);
            netloc = delimiter < 0 ? rest : rest[..delimiter];
            url = delimiter < 0 ? string.Empty : rest[delimiter..];
            if ((netloc.Contains('[', StringComparison.Ordinal) && !netloc.Contains(']', StringComparison.Ordinal)) ||
                (netloc.Contains(']', StringComparison.Ordinal) && !netloc.Contains('[', StringComparison.Ordinal)))
            {
                throw new PyValueErrorException("Invalid IPv6 URL");
            }

            if (netloc.Contains('[', StringComparison.Ordinal) && netloc.Contains(']', StringComparison.Ordinal))
            {
                var bracketed = netloc[(netloc.IndexOf('[', StringComparison.Ordinal) + 1)..];
                bracketed = bracketed[..bracketed.IndexOf(']', StringComparison.Ordinal)];
                if (bracketed.StartsWith('v'))
                {
                    if (!System.Text.RegularExpressions.Regex.IsMatch(bracketed, @"\Av[a-fA-F0-9]+\..+\z"))
                    {
                        throw new PyValueErrorException("IPvFuture address is invalid");
                    }
                }
                else if (!PyIpAddress.TryParse(bracketed, out var ip))
                {
                    throw new PyValueErrorException($"{PyStrings.Repr(bracketed)} does not appear to be an IPv4 or IPv6 address");
                }
                else if (!ip.IsV6)
                {
                    throw new PyValueErrorException("An IPv4 address cannot be in brackets");
                }
            }
        }

        var hash = url.IndexOf('#', StringComparison.Ordinal);
        if (hash >= 0)
        {
            fragment = url[(hash + 1)..];
            url = url[..hash];
        }

        var question = url.IndexOf('?', StringComparison.Ordinal);
        if (question >= 0)
        {
            query = url[(question + 1)..];
            url = url[..question];
        }

        return new SplitUrl(scheme, netloc, url, query, fragment);
    }
}

/// <summary>Port of the URL policy in <c>weir.platform.outbound_http</c>.</summary>
public static class ExternalUrlPolicy
{
    /// <summary><c>validate_external_provider_url</c>: refuses localhost and private addresses written literally.</summary>
    public static string ValidateExternalProviderUrl(string raw)
    {
        ArgumentNullException.ThrowIfNull(raw);
        var parsed = SplitUrl.Parse(raw.Trim());
        if (parsed.Scheme is not ("http" or "https"))
        {
            throw new PyValueErrorException($"Blocked provider URL scheme: {(parsed.Scheme.Length == 0 ? "<missing>" : parsed.Scheme)}");
        }

        var host = (parsed.Hostname ?? string.Empty).Trim().ToLowerInvariant();
        if (host.Length == 0)
        {
            throw new PyValueErrorException("Blocked provider URL host: <missing>");
        }

        if (host is "localhost" or "127.0.0.1" or "::1" or "0.0.0.0")
        {
            throw new PyValueErrorException($"Blocked provider URL host: {host}");
        }

        if (!PyIpAddress.TryParse(host, out var ip))
        {
            return raw;
        }

        if (ip.IsLoopback || ip.IsLinkLocal || ip.IsPrivate || ip.IsMulticast || ip.IsReserved || ip.IsUnspecified)
        {
            throw new PyValueErrorException($"Blocked provider URL host: {host}");
        }

        return raw;
    }

    /// <summary><c>normalize_local_service_base_url</c>.</summary>
    public static string NormalizeLocalServiceBaseUrl(string raw)
    {
        ArgumentNullException.ThrowIfNull(raw);
        var parsed = SplitUrl.Parse(raw.Trim().TrimEnd('/'));
        if (parsed.Scheme is not ("http" or "https") || parsed.Hostname is null)
        {
            throw new PyValueErrorException("URL must be a valid http(s) URL.");
        }

        if (!string.IsNullOrEmpty(parsed.Username) || !string.IsNullOrEmpty(parsed.Password) || parsed.Query.Length > 0 || parsed.Fragment.Length > 0)
        {
            throw new PyValueErrorException("URL must not include credentials, query strings, or fragments.");
        }

        return parsed.Scheme + "://" + parsed.Netloc + parsed.Path.TrimEnd('/');
    }

    public const string InvalidDestination = "The notification destination must be a valid external HTTP(S) address.";
    public const string EmbeddedCredentials = "The notification destination must not contain embedded credentials.";
    public const string InvalidPort = "The notification destination has an invalid port.";
    public const string CouldNotResolve = "Weir could not resolve the notification destination.";
    public const string NonPublicAddress = "The notification destination resolved to a non-public network address.";
    public const string CouldNotConnect = "Weir could not connect to the notification destination.";
    public const string CouldNotSecure = "Weir could not establish secure notification delivery.";
    public const string RedirectRefused = "The notification destination returned a redirect; redirects are disabled.";
    public const string CouldNotDeliver = "Weir could not deliver the notification.";
    public const string GenericDeliveryError = "Weir could not deliver the notification. Check the destination and server logs.";
}
