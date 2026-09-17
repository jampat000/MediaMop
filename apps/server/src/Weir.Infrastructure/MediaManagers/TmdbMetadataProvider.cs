using System.Globalization;
using System.Net.Http.Headers;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Notifications;
using Weir.Core.Rules;
using Weir.Core.Security;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>One metadata provider (<c>MetadataProvider</c>). Implementations never throw.</summary>
public interface IMetadataProvider
{
    string Name { get; }

    Task<LookupResult> LookupMovieAsync(string title, int? year, CancellationToken cancellationToken = default);

    Task<LookupResult> TestConnectionAsync(CancellationToken cancellationToken = default);
}

/// <summary>Bounded, thread-safe, oldest-first lookup cache, shared across passes within one process (<c>_Cache</c>).</summary>
public sealed class MetadataLookupCache
{
    private readonly Lock _lock = new();
    private readonly LinkedList<(string Key, LookupResult Value)> _order = new();
    private readonly Dictionary<string, LinkedListNode<(string Key, LookupResult Value)>> _entries = new(StringComparer.Ordinal);
    private readonly int _max;

    public MetadataLookupCache(int maxEntries = TmdbResponses.CacheMaxEntries)
    {
        _max = maxEntries;
    }

    /// <summary>The process-wide cache (<c>_SHARED_CACHE</c>).</summary>
    public static MetadataLookupCache Shared { get; } = new();

    public int Count
    {
        get
        {
            lock (_lock)
            {
                return _entries.Count;
            }
        }
    }

    public LookupResult? Get(string key)
    {
        lock (_lock)
        {
            if (!_entries.TryGetValue(key, out var node))
            {
                return null;
            }

            _order.Remove(node);
            _order.AddLast(node);
            return node.Value.Value;
        }
    }

    public void Put(string key, LookupResult value)
    {
        lock (_lock)
        {
            if (_entries.TryGetValue(key, out var existing))
            {
                _order.Remove(existing);
            }

            _entries[key] = _order.AddLast((key, value));
            while (_entries.Count > _max && _order.First is { } oldest)
            {
                _order.RemoveFirst();
                _entries.Remove(oldest.Value.Key);
            }
        }
    }

    /// <summary><c>clear_metadata_cache</c>: used by tests and after a credential change.</summary>
    public void Clear()
    {
        lock (_lock)
        {
            _entries.Clear();
            _order.Clear();
        }
    }
}

/// <summary>
/// TMDb over its v3 API, directly or through a gateway (port of <c>tmdb_provider.TmdbMetadataProvider</c>). The base URL
/// is checked with <see cref="ExternalUrlPolicy.ValidateExternalProviderUrl"/>, so localhost and private addresses are refused.
/// </summary>
public sealed class TmdbMetadataProvider : IMetadataProvider
{
    private readonly string _apiKey;
    private readonly string _baseUrl;
    private readonly MetadataLookupCache _cache;
    private readonly IManagerHttpHandlerFactory _handlers;
    private readonly TimeProvider _time;
    private readonly Lock _rateLock = new();
    private DateTimeOffset? _nextSlot;

    public TmdbMetadataProvider(string apiKey, IManagerHttpHandlerFactory handlers, string baseUrl = TmdbResponses.DefaultBaseUrl, MetadataLookupCache? cache = null, TimeProvider? time = null)
    {
        _apiKey = PyStrings.Strip(apiKey ?? string.Empty);
        var trimmed = PyStrings.Strip(string.IsNullOrEmpty(baseUrl) ? TmdbResponses.DefaultBaseUrl : baseUrl).TrimEnd('/');
        _baseUrl = trimmed;
        _cache = cache ?? MetadataLookupCache.Shared;
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
        _time = time ?? TimeProvider.System;
    }

    public string Name => "tmdb";

    /// <summary><c>lookup_movie</c>: every failure is a status, never an exception. Negative answers are cached too.</summary>
    public async Task<LookupResult> LookupMovieAsync(string title, int? year, CancellationToken cancellationToken = default)
    {
        var cleaned = PyStrings.Strip(title ?? string.Empty);
        if (cleaned.Length == 0)
        {
            return new LookupResult { Status = LookupResult.StatusNoMatch, Detail = "There was no title to look up." };
        }

        if (_apiKey.Length == 0)
        {
            return new LookupResult
            {
                Status = LookupResult.StatusNotConfigured,
                Detail = "No metadata provider key is configured, so Weir used the language preference list.",
            };
        }

        var key = TmdbResponses.CacheKey(_baseUrl, cleaned, year);
        if (_cache.Get(key) is { } cached)
        {
            return cached;
        }

        var parameters = new List<KeyValuePair<string, string>> { new("api_key", _apiKey), new("query", cleaned) };
        if (year is { } y && y != 0)
        {
            parameters.Add(new("year", y.ToString(CultureInfo.InvariantCulture)));
        }

        var result = await SearchAsync(parameters, TmdbResponses.Subject(cleaned, year), useRateLimit: true, cancellationToken).ConfigureAwait(false);
        _cache.Put(key, result);
        return result;
    }

    /// <summary><c>test_connection</c>: a cheap real query, so a saved key is proven rather than assumed.</summary>
    public async Task<LookupResult> TestConnectionAsync(CancellationToken cancellationToken = default)
    {
        if (_apiKey.Length == 0)
        {
            return new LookupResult { Status = LookupResult.StatusNotConfigured, Detail = "No metadata provider key is configured." };
        }

        var probe = await SearchAsync(
            [new("api_key", _apiKey), new("query", "Blade Runner"), new("year", "1982")],
            "the connection test",
            useRateLimit: false,
            cancellationToken).ConfigureAwait(false);
        return probe.Status == LookupResult.StatusMatched
            ? new LookupResult { Status = LookupResult.StatusMatched, Metadata = probe.Metadata, Detail = "The metadata provider answered." }
            : probe;
    }

    /// <summary>One call per interval: each caller reserves the next free slot, then waits for it.</summary>
    private async Task WaitForRateLimitAsync(CancellationToken cancellationToken)
    {
        TimeSpan wait;
        lock (_rateLock)
        {
            var now = _time.GetUtcNow();
            wait = _nextSlot is { } slot && slot > now ? slot - now : TimeSpan.Zero;
            _nextSlot = now + wait + TmdbResponses.MinimumBetweenCalls;
        }

        if (wait > TimeSpan.Zero)
        {
            await Task.Delay(wait, _time, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task<LookupResult> SearchAsync(List<KeyValuePair<string, string>> parameters, string subject, bool useRateLimit, CancellationToken cancellationToken)
    {
        string baseUrl;
        try
        {
            baseUrl = ExternalUrlPolicy.ValidateExternalProviderUrl(_baseUrl);
        }
        catch (PyValueErrorException exception)
        {
            return new LookupResult { Status = LookupResult.StatusNotConfigured, Detail = $"The metadata provider address is not usable ({exception.Message})." };
        }

        if (useRateLimit)
        {
            await WaitForRateLimitAsync(cancellationToken).ConfigureAwait(false);
        }

        byte[] body;
        try
        {
            using var client = new HttpClient(_handlers.Handler(followRedirects: true), disposeHandler: false) { Timeout = TmdbResponses.Timeout };
            using var request = new HttpRequestMessage(HttpMethod.Get, $"{baseUrl}/search/movie?{TmdbResponses.UrlEncode(parameters)}");
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            using var response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
            var status = (int)response.StatusCode;
            if (status is < 200 or >= 300)
            {
                return status is 401 or 403
                    ? new LookupResult { Status = LookupResult.StatusNotConfigured, Detail = "The metadata provider rejected the configured key." }
                    : new LookupResult { Status = LookupResult.StatusUnreachable, Detail = $"The metadata provider returned HTTP {status.ToString(CultureInfo.InvariantCulture)} for {subject}." };
            }

            body = await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (MediaManagerHttpClient.IsTransportFailure(exception, cancellationToken) || exception is UriFormatException or InvalidOperationException)
        {
            return new LookupResult { Status = LookupResult.StatusUnreachable, Detail = $"Weir could not reach the metadata provider ({exception.Message})." };
        }

        return TmdbResponses.Parse(body, subject);
    }
}

/// <summary>Building the configured provider and testing it (port of <c>integrations.metadata.provider_service</c>).</summary>
public sealed class MetadataProviderService
{
    private readonly CredentialCipher _cipher;
    private readonly IManagerHttpHandlerFactory _handlers;

    public MetadataProviderService(CredentialCipher cipher, IManagerHttpHandlerFactory handlers)
    {
        _cipher = cipher ?? throw new ArgumentNullException(nameof(cipher));
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
    }

    /// <summary><c>store_provider_key</c>: encrypted with the manager-credential envelope, or empty.</summary>
    public string StoreProviderKey(string plaintext)
    {
        ArgumentNullException.ThrowIfNull(plaintext);
        return PyStrings.Strip(plaintext).Length > 0 ? _cipher.Encrypt(plaintext) : string.Empty;
    }

    /// <summary><c>build_provider</c>: null is a normal answer; every caller degrades to the language preferences.</summary>
    public async Task<IMetadataProvider?> BuildProviderAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var row = await uow.QuerySingleAsync(
            "SELECT metadata_provider, metadata_provider_key_ciphertext, metadata_provider_base_url FROM suite_settings WHERE id = 1",
            reader => new[] { SqliteValues.GetString(reader, 0), SqliteValues.GetString(reader, 1), SqliteValues.GetString(reader, 2) }).ConfigureAwait(false);
        if (row is null)
        {
            return null;
        }

        var name = PyStrings.Strip(row[0]).ToLowerInvariant();
        if (!TmdbResponses.KnownProviders.Contains(name))
        {
            return null;
        }

        var ciphertext = PyStrings.Strip(row[1]);
        var key = ciphertext.Length > 0 ? _cipher.Decrypt(ciphertext) ?? string.Empty : string.Empty;
        if (key.Length == 0)
        {
            return null;
        }

        var baseUrl = PyStrings.Strip(row[2]);
        return new TmdbMetadataProvider(key, _handlers, baseUrl.Length > 0 ? baseUrl : TmdbResponses.DefaultBaseUrl);
    }

    /// <summary><c>test_provider</c>: prove a saved connection works rather than assuming it.</summary>
    public async Task<LookupResult> TestProviderAsync(UnitOfWork uow, CancellationToken cancellationToken = default)
    {
        var provider = await BuildProviderAsync(uow).ConfigureAwait(false);
        return provider is null
            ? new LookupResult
            {
                Status = LookupResult.StatusNotConfigured,
                Detail = "No metadata provider is configured, so Weir uses the language preferences on each rule set.",
            }
            : await provider.TestConnectionAsync(cancellationToken).ConfigureAwait(false);
    }
}
