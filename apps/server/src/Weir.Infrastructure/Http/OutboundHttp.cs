using System.Net;
using System.Net.Http.Headers;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using Weir.Core;
using Weir.Core.Json;
using Weir.Core.Net;
using Weir.Core.Notifications;
using Weir.Core.Updates;

namespace Weir.Infrastructure.Http;

/// <summary>Fetches the latest GitHub release (port of <c>fetch_latest_release_record</c>).</summary>
public interface IReleaseCatalogClient
{
    /// <summary>Throws <see cref="ReleaseFetchException"/> for an HTTP error status, other exceptions for anything else.</summary>
    Task<GitHubReleaseRecord> FetchLatestAsync(string userAgentVersion, CancellationToken cancellationToken);
}

public sealed class GitHubReleaseCatalogClient : IReleaseCatalogClient
{
    public async Task<GitHubReleaseRecord> FetchLatestAsync(string userAgentVersion, CancellationToken cancellationToken)
    {
        using var client = new HttpClient(new SocketsHttpHandler { AllowAutoRedirect = true }) { Timeout = TimeSpan.FromSeconds(5) };
        using var request = new HttpRequestMessage(HttpMethod.Get, ReleaseCatalog.LatestReleaseUrl);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        request.Headers.TryAddWithoutValidation("User-Agent", $"Weir/{userAgentVersion}");
        request.Headers.Add("X-GitHub-Api-Version", "2022-11-28");
        using var response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        if ((int)response.StatusCode >= 400)
        {
            throw new ReleaseFetchException((int)response.StatusCode);
        }

        var bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
        return ReleaseCatalog.CoerceReleasePayload(PyJsonParser.ParseBytes(bytes));
    }
}

/// <summary>An operator-facing failure to reach or use an external endpoint (<c>ExternalEndpointError</c>).</summary>
public sealed class ExternalEndpointException : Exception
{
    public ExternalEndpointException()
    {
    }

    public ExternalEndpointException(string message)
        : base(message)
    {
    }

    public ExternalEndpointException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>Posts JSON to a public endpoint (port of <c>post_json_to_external_url</c>).</summary>
public interface IExternalJsonPoster
{
    Task<int> PostJsonAsync(string url, byte[] body, IReadOnlyDictionary<string, string> headers, TimeSpan timeout, CancellationToken cancellationToken);
}

/// <summary>
/// Resolves the host, refuses any non-public answer, connects to exactly the validated address with no
/// redirects and TLS 1.2 or newer, as <c>weir.platform.outbound_http</c> does.
/// </summary>
public sealed class ExternalJsonPoster : IExternalJsonPoster
{
    public async Task<int> PostJsonAsync(string url, byte[] body, IReadOnlyDictionary<string, string> headers, TimeSpan timeout, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(body);
        ArgumentNullException.ThrowIfNull(headers);
        var endpoint = await ResolveAsync(url, cancellationToken).ConfigureAwait(false);
        using var handler = new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseProxy = false,
            ConnectTimeout = timeout,
            SslOptions = new SslClientAuthenticationOptions { EnabledSslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13 },
            ConnectCallback = async (context, token) =>
            {
                var socket = new Socket(SocketType.Stream, ProtocolType.Tcp) { NoDelay = true };
                try
                {
                    await socket.ConnectAsync(endpoint.Address, endpoint.Port, token).ConfigureAwait(false);
                    return new NetworkStream(socket, ownsSocket: true);
                }
                catch (Exception exception) when (exception is SocketException or OperationCanceledException)
                {
                    socket.Dispose();
                    throw new ExternalEndpointException(ExternalUrlPolicy.CouldNotConnect, exception);
                }
            },
        };
        using var client = new HttpClient(handler) { Timeout = timeout };
        using var request = new HttpRequestMessage(HttpMethod.Post, endpoint.Uri) { Content = new ByteArrayContent(body) };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
        foreach (var (name, value) in headers)
        {
            if (!request.Headers.TryAddWithoutValidation(name, value))
            {
                request.Content.Headers.TryAddWithoutValidation(name, value);
            }
        }

        HttpResponseMessage response;
        try
        {
            response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
        }
        catch (HttpRequestException exception) when (exception.InnerException is ExternalEndpointException inner)
        {
            throw new ExternalEndpointException(inner.Message, exception);
        }
        catch (HttpRequestException exception) when (exception.InnerException is AuthenticationException or IOException && endpoint.Uri.Scheme == "https")
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.CouldNotSecure, exception);
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException or TaskCanceledException)
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.CouldNotDeliver, exception);
        }

        using (response)
        {
            var status = (int)response.StatusCode;
            if (status is >= 300 and < 400)
            {
                throw new ExternalEndpointException(ExternalUrlPolicy.RedirectRefused);
            }

            return status;
        }
    }

    private sealed record ResolvedEndpoint(Uri Uri, IPAddress Address, int Port);

    /// <summary><c>resolve_public_external_endpoint</c>.</summary>
    private static async Task<ResolvedEndpoint> ResolveAsync(string raw, CancellationToken cancellationToken)
    {
        SplitUrl parsed;
        try
        {
            parsed = SplitUrl.Parse((raw ?? string.Empty).Trim());
        }
        catch (PyValueErrorException exception)
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.InvalidDestination, exception);
        }

        var hostname = parsed.Hostname;
        if (parsed.Scheme is not ("http" or "https") || hostname is null)
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.InvalidDestination);
        }

        if (!string.IsNullOrEmpty(parsed.Username) || !string.IsNullOrEmpty(parsed.Password))
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.EmbeddedCredentials);
        }

        int port;
        try
        {
            port = parsed.Port is { } explicitPort && explicitPort != 0 ? explicitPort : parsed.Scheme == "https" ? 443 : 80;
        }
        catch (PyValueErrorException exception)
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.InvalidPort, exception);
        }

        IPAddress[] addresses;
        try
        {
            addresses = PyIpAddress.TryParse(hostname, out _) && IPAddress.TryParse(hostname, out var literal)
                ? [literal]
                : await Dns.GetHostAddressesAsync(hostname, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is SocketException or ArgumentException)
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.CouldNotResolve, exception);
        }

        var distinct = addresses.Select(a => a.IsIPv4MappedToIPv6 ? a.MapToIPv4() : a).Distinct().ToList();
        if (distinct.Count == 0 || distinct.Any(address => !PyIpAddress.FromIpAddress(address).IsGlobal))
        {
            throw new ExternalEndpointException(ExternalUrlPolicy.NonPublicAddress);
        }

        var path = parsed.Path.Length == 0 ? "/" : parsed.Path;
        if (parsed.Query.Length > 0)
        {
            path += "?" + parsed.Query;
        }

        var host = hostname.Contains(':', StringComparison.Ordinal) ? $"[{hostname}]" : hostname;
        var uri = new Uri($"{parsed.Scheme}://{host}:{port}{path}");
        return new ResolvedEndpoint(uri, distinct[0], port);
    }
}

/// <summary>Port of <c>weir.platform.notifications.dispatch</c>.</summary>
public sealed class NotificationDispatcher
{
    public const string TestTitle = "Weir test notification";
    public const string TestDetail = "This is a test notification from Weir.";

    private static readonly TimeSpan DispatchTimeout = TimeSpan.FromSeconds(10);
    private readonly IExternalJsonPoster _poster;
    private readonly TimeProvider _time;

    public NotificationDispatcher(IExternalJsonPoster poster, TimeProvider time)
    {
        _poster = poster;
        _time = time;
    }

    /// <summary><c>_post_one</c>.</summary>
    public Task<int> PostOneAsync(NotificationChannelRecord channel, string title, string detail, string jobEvent, string module, long jobId, string jobKind, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(channel);
        var now = Core.Time.PyDateTime.UtcNow(_time);
        var body = channel.Provider == "discord"
            ? NotificationRules.DiscordPayload(title, detail, jobEvent, module, jobId, now)
            : NotificationRules.WebhookPayload(jobEvent, module, jobId, jobKind, title, detail, now);
        return _poster.PostJsonAsync(channel.Url, body, new Dictionary<string, string>(StringComparer.Ordinal) { ["User-Agent"] = "Weir/1.0" }, DispatchTimeout, cancellationToken);
    }

    /// <summary><c>test_dispatch_notification_channel</c>: the error text, or <see langword="null"/> on success.</summary>
    public async Task<string?> TestAsync(NotificationChannelRecord channel, CancellationToken cancellationToken)
    {
        try
        {
            await PostOneAsync(channel, TestTitle, TestDetail, "job_completed", "refiner", 0, "test", cancellationToken).ConfigureAwait(false);
            return null;
        }
        catch (ExternalEndpointException exception)
        {
            return exception.Message;
        }
        catch (Exception exception) when (exception is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
        {
            return ExternalUrlPolicy.GenericDeliveryError;
        }
    }

    /// <summary>The version string a request's <c>User-Agent</c> names.</summary>
    public static string UserAgentVersion(string? versionOverride) => WeirVersion.Resolve(versionOverride);

    /// <summary>
    /// <c>dispatch_job_notification</c>: send <c>{module}_job_{eventKind}</c> to every enabled channel subscribed
    /// to it or to its generic form, without the caller waiting. For <c>failed</c> the job must be permanently
    /// failed. Never throws; failures are logged through <paramref name="warn"/>.
    /// </summary>
    public void DispatchJobNotification(
        Sqlite.SqliteDatabase database, string module, string eventKind, long jobId, string jobKind, Action<string, Exception?> warn)
    {
        ArgumentNullException.ThrowIfNull(database);
        ArgumentNullException.ThrowIfNull(warn);
        var (jobEvent, title, detail) = NotificationRules.JobNotification(module, eventKind, jobId, jobKind);
        _ = Task.Run(async () =>
        {
            List<NotificationChannelRecord> channels;
            try
            {
                var uow = await Sqlite.UnitOfWork.OpenAsync(database).ConfigureAwait(false);
                await using (uow.ConfigureAwait(false))
                {
                    if (eventKind == "failed" && module == "refiner")
                    {
                        var status = await uow.ScalarAsync("SELECT status FROM refiner_jobs WHERE id = $id", ("$id", jobId)).ConfigureAwait(false);
                        if (status is not string text || text != "failed")
                        {
                            return;
                        }
                    }

                    channels = await Notifications.NotificationChannelStore.ForEventAsync(uow, jobEvent).ConfigureAwait(false);
                    var generic = jobEvent.StartsWith(module + "_", StringComparison.Ordinal) ? jobEvent[(module.Length + 1)..] : jobEvent;
                    if (generic != jobEvent)
                    {
                        foreach (var channel in await Notifications.NotificationChannelStore.ForEventAsync(uow, generic).ConfigureAwait(false))
                        {
                            if (!channels.Any(existing => existing.Id == channel.Id))
                            {
                                channels.Add(channel);
                            }
                        }
                    }
                }
            }
            catch (Exception exception) when (exception is Microsoft.Data.Sqlite.SqliteException or IOException or InvalidOperationException)
            {
                warn($"Notification dispatch: failed to read channels for event={jobEvent}", exception);
                return;
            }

            foreach (var channel in channels)
            {
                try
                {
                    var status = await PostOneAsync(channel, title, detail, jobEvent, module, jobId, jobKind, CancellationToken.None).ConfigureAwait(false);
                    if (status >= 400)
                    {
                        warn($"Notification channel {channel.Id} ({channel.Label}) returned HTTP {status} for event={jobEvent}", null);
                    }
                }
                catch (Exception exception) when (exception is ExternalEndpointException or HttpRequestException or IOException or OperationCanceledException)
                {
                    var message = exception is ExternalEndpointException ? exception.Message : ExternalUrlPolicy.GenericDeliveryError;
                    warn($"Notification dispatch failed for channel {channel.Id} ({channel.Label}) event={jobEvent}: {message}", null);
                }
            }
        });
    }
}
