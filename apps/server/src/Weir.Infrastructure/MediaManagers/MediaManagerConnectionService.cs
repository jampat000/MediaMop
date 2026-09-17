using System.Security.Cryptography;
using System.Text;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Notifications;
using Weir.Core.Security;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>A connection could not be saved as asked, with an operator-readable reason (<c>MediaManagerConnectionError</c>).</summary>
public sealed class MediaManagerConnectionException : Exception
{
    public MediaManagerConnectionException()
    {
    }

    public MediaManagerConnectionException(string message)
        : base(message)
    {
    }

    public MediaManagerConnectionException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>Where to report a finished hand-off, and how to authenticate (<c>ResolvedCallbackTarget</c>).</summary>
public sealed record ResolvedCallbackTarget(string BaseUrl, string? ApiKey);

/// <summary>
/// Reading and writing connections with their secrets encrypted, and resolving which managers look after a scope
/// (ports of <c>connection_service</c> and <c>manager_binding</c>).
/// </summary>
public sealed class MediaManagerConnectionService
{
    private const string NeedsNameMessage = "Give the connection a name so you can tell it apart later.";

    private readonly WeirOptions _options;
    private readonly CredentialCipher _cipher;
    private readonly IMediaManagerPorts _ports;

    public MediaManagerConnectionService(WeirOptions options, CredentialCipher cipher, IMediaManagerPorts ports)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _cipher = cipher ?? throw new ArgumentNullException(nameof(cipher));
        _ports = ports ?? throw new ArgumentNullException(nameof(ports));
    }

    public CredentialCipher Cipher => _cipher;

    public IMediaManagerPorts Ports => _ports;

    /// <summary><c>create_connection</c>. Throws <see cref="MediaManagerConnectionException"/> for an operator mistake.</summary>
    public async Task<long> CreateAsync(UnitOfWork uow, string kind, string name, string baseUrl = "", string? apiKey = null, bool enabled = true)
    {
        ArgumentNullException.ThrowIfNull(uow);
        var label = PyStrings.Strip(name ?? string.Empty);
        if (label.Length == 0)
        {
            throw new MediaManagerConnectionException(NeedsNameMessage);
        }

        if (await MediaManagerConnectionStore.NameExistsAsync(uow, label).ConfigureAwait(false))
        {
            throw new MediaManagerConnectionException($"A connection named {PyStrings.Repr(label)} already exists.");
        }

        var key = PyStrings.Strip(apiKey ?? string.Empty);
        var validKind = ValidateKind(kind);
        var validUrl = ValidateBaseUrl(baseUrl);
        var ciphertext = key.Length > 0 ? EncryptApiKey(key) : null;
        return await MediaManagerConnectionStore.InsertAsync(uow, validKind, label, enabled, validUrl, ciphertext).ConfigureAwait(false);
    }

    /// <summary><c>update_connection</c>: <see langword="null"/> leaves a field alone; an empty <paramref name="apiKey"/> clears the key.</summary>
    public async Task UpdateAsync(UnitOfWork uow, MediaManagerConnectionRecord row, string? name = null, string? baseUrl = null, string? apiKey = null, bool? enabled = null)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(row);
        var changes = new List<(string Column, object? Value)>();
        if (name is not null)
        {
            var label = PyStrings.Strip(name);
            if (label.Length == 0)
            {
                throw new MediaManagerConnectionException(NeedsNameMessage);
            }

            if (await MediaManagerConnectionStore.NameExistsAsync(uow, label, row.Id).ConfigureAwait(false))
            {
                throw new MediaManagerConnectionException($"A connection named {PyStrings.Repr(label)} already exists.");
            }

            if (label != row.Name)
            {
                changes.Add(("name", label));
            }
        }

        if (baseUrl is not null)
        {
            var validUrl = ValidateBaseUrl(baseUrl);
            if (validUrl != row.BaseUrl)
            {
                changes.Add(("base_url", validUrl));
            }
        }

        if (enabled is { } flag && flag != row.Enabled)
        {
            changes.Add(("enabled", flag ? 1 : 0));
        }

        if (apiKey is not null)
        {
            var stripped = PyStrings.Strip(apiKey);
            var ciphertext = stripped.Length > 0 ? EncryptApiKey(stripped) : null;
            if (ciphertext != row.ApiKeyCiphertext)
            {
                changes.Add(("api_key_ciphertext", ciphertext));
            }
        }

        await MediaManagerConnectionStore.UpdateColumnsAsync(uow, row.Id, changes).ConfigureAwait(false);
    }

    /// <summary><c>rotate_webhook_secret</c>: a fresh inbound secret, stored encrypted and returned once.</summary>
    public async Task<string> RotateWebhookSecretAsync(UnitOfWork uow, MediaManagerConnectionRecord row)
    {
        ArgumentNullException.ThrowIfNull(row);
        var plaintext = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        await MediaManagerConnectionStore.UpdateColumnsAsync(uow, row.Id, [("webhook_secret_ciphertext", _cipher.Encrypt(plaintext))]).ConfigureAwait(false);
        return plaintext;
    }

    /// <summary><c>webhook_secret_matches</c>: a connection with no secret requires none.</summary>
    public bool WebhookSecretMatches(MediaManagerConnectionRecord row, string? presented)
    {
        ArgumentNullException.ThrowIfNull(row);
        if (string.IsNullOrEmpty(row.WebhookSecretCiphertext))
        {
            return true;
        }

        var expected = _cipher.Decrypt(row.WebhookSecretCiphertext);
        return !string.IsNullOrEmpty(expected) && CompareDigest(expected, PyStrings.Strip(presented ?? string.Empty));
    }

    /// <summary><c>resolve_callback_target</c>.</summary>
    public ResolvedCallbackTarget? ResolveCallbackTarget(MediaManagerConnectionRecord row)
    {
        ArgumentNullException.ThrowIfNull(row);
        var baseUrl = PyStrings.Strip(row.BaseUrl);
        if (baseUrl.Length == 0)
        {
            return null;
        }

        var apiKey = string.IsNullOrEmpty(row.ApiKeyCiphertext) ? null : _cipher.Decrypt(row.ApiKeyCiphertext);
        return new ResolvedCallbackTarget(baseUrl.TrimEnd('/'), apiKey);
    }

    /// <summary><c>secrets.compare_digest</c> over the text.</summary>
    public static bool CompareDigest(string left, string right) =>
        CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(left ?? string.Empty), Encoding.UTF8.GetBytes(right ?? string.Empty));

    // --- manager_binding -----------------------------------------------------------------------

    /// <summary><c>_connection_from_row</c>: null when the row has no address or no key that decrypts.</summary>
    public ManagerConnection? ConnectionFromRow(MediaManagerConnectionRecord row)
    {
        ArgumentNullException.ThrowIfNull(row);
        var url = PyStrings.Strip(row.BaseUrl);
        var ciphertext = PyStrings.Strip(row.ApiKeyCiphertext ?? string.Empty);
        if (url.Length == 0 || ciphertext.Length == 0)
        {
            return null;
        }

        var key = _cipher.Decrypt(ciphertext);
        return string.IsNullOrEmpty(key) ? null : new ManagerConnection(row.Kind, row.Name, url, key, row.Id);
    }

    /// <summary><c>connections_for_scope</c>: every enabled, credentialed manager for the scope; the environment only when nothing claims it.</summary>
    public async Task<List<ManagerConnection>> ConnectionsForScopeAsync(UnitOfWork uow, string mediaScope)
    {
        var rows = await MediaManagerConnectionStore.ListEnabledAsync(uow).ConfigureAwait(false);
        var serving = rows.Where(row => _ports.PortForKind(row.Kind) is { } port && port.Capabilities().Scopes.Contains(mediaScope)).ToList();
        var resolved = serving.Select(ConnectionFromRow).OfType<ManagerConnection>().ToList();
        if (resolved.Count > 0)
        {
            return resolved;
        }

        if (serving.Count > 0)
        {
            return [];
        }

        return HttpMediaManagerPorts.EnvironmentConnectionForScope(_options, mediaScope) is { } environment ? [environment] : [];
    }

    /// <summary><c>all_enabled_connections</c>.</summary>
    public async Task<List<ManagerConnection>> AllEnabledConnectionsAsync(UnitOfWork uow) =>
        [.. (await MediaManagerConnectionStore.ListEnabledAsync(uow).ConfigureAwait(false)).Select(ConnectionFromRow).OfType<ManagerConnection>()];

    /// <summary><c>connections_by_id</c>: exactly the enabled connections named, in id order; half-configured ones dropped.</summary>
    public async Task<List<ManagerConnection>> ConnectionsByIdAsync(UnitOfWork uow, IEnumerable<long> connectionIds)
    {
        ArgumentNullException.ThrowIfNull(connectionIds);
        var wanted = connectionIds.ToHashSet();
        if (wanted.Count == 0)
        {
            return [];
        }

        var rows = await MediaManagerConnectionStore.ListEnabledAsync(uow).ConfigureAwait(false);
        return [.. rows.Where(row => wanted.Contains(row.Id)).Select(ConnectionFromRow).OfType<ManagerConnection>()];
    }

    /// <summary><c>collect_queue_signals</c>: every covering manager's answer, rows narrowed to the scope asked about.</summary>
    public async Task<IReadOnlyList<ManagerQueueSignal>> CollectQueueSignalsAsync(UnitOfWork uow, string mediaScope, IReadOnlyCollection<long>? connectionIds = null, CancellationToken cancellationToken = default)
    {
        var resolved = connectionIds is not null
            ? await ConnectionsByIdAsync(uow, connectionIds).ConfigureAwait(false)
            : await ConnectionsForScopeAsync(uow, mediaScope).ConfigureAwait(false);
        var signals = new List<ManagerQueueSignal>();
        foreach (var connection in resolved)
        {
            if (_ports.PortForKind(connection.Kind) is not { } port)
            {
                continue;
            }

            signals.Add(ManagerDialectRules.OnlyRowsForScope(await port.QueueRowsAsync(connection, cancellationToken).ConfigureAwait(false), mediaScope));
        }

        return signals;
    }

    /// <summary><c>collect_library_truth</c>.</summary>
    public async Task<IReadOnlyList<ManagerLibraryTruth>> CollectLibraryTruthAsync(UnitOfWork uow, string mediaScope, IReadOnlyCollection<long>? connectionIds = null, CancellationToken cancellationToken = default)
    {
        var resolved = connectionIds is not null
            ? await ConnectionsByIdAsync(uow, connectionIds).ConfigureAwait(false)
            : await ConnectionsForScopeAsync(uow, mediaScope).ConfigureAwait(false);
        var answers = new List<ManagerLibraryTruth>();
        foreach (var connection in resolved)
        {
            if (_ports.PortForKind(connection.Kind) is not { } port)
            {
                continue;
            }

            answers.Add(await port.LibraryTruthAsync(connection, mediaScope, cancellationToken).ConfigureAwait(false));
        }

        return answers;
    }

    /// <summary><c>describe_connections</c>: what each enabled, credentialed manager says it manages.</summary>
    public async Task<IReadOnlyList<ManagerDescription>> DescribeConnectionsAsync(UnitOfWork uow, CancellationToken cancellationToken = default)
    {
        var described = new List<ManagerDescription>();
        foreach (var connection in await AllEnabledConnectionsAsync(uow).ConfigureAwait(false))
        {
            if (_ports.PortForKind(connection.Kind) is not { } port)
            {
                continue;
            }

            described.Add(await port.DescribeAsync(connection, cancellationToken).ConfigureAwait(false));
        }

        return described;
    }

    /// <summary>
    /// #544 item 3: <c>encrypt_arr_api_key</c> raises a plain <see cref="PyValueErrorException"/> when no
    /// <c>WEIR_CREDENTIALS_SECRET</c> or <c>WEIR_SESSION_SECRET</c> is configured. Python's <c>create_connection</c>
    /// and <c>update_connection</c> let that escape uncaught (a 500); here it becomes the same operator-readable
    /// 400 as any other <see cref="MediaManagerConnectionException"/>, still naming the env var to set.
    /// </summary>
    private string EncryptApiKey(string plaintext)
    {
        try
        {
            return _cipher.Encrypt(plaintext);
        }
        catch (PyValueErrorException exception)
        {
            throw new MediaManagerConnectionException(exception.Message, exception);
        }
    }

    private static string ValidateKind(string? kind)
    {
        var value = PyStrings.Strip(kind ?? string.Empty).ToLowerInvariant();
        if (!MediaManagerKinds.All.Contains(value))
        {
            throw new MediaManagerConnectionException(
                $"Unknown media manager kind {PyStrings.Repr(kind ?? string.Empty)}. Known kinds: {string.Join(", ", MediaManagerKinds.All)}.");
        }

        return value;
    }

    private static string ValidateBaseUrl(string? baseUrl)
    {
        var raw = PyStrings.Strip(baseUrl ?? string.Empty);
        if (raw.Length == 0)
        {
            return string.Empty;
        }

        try
        {
            return ExternalUrlPolicy.NormalizeLocalServiceBaseUrl(raw);
        }
        catch (PyValueErrorException exception)
        {
            throw new MediaManagerConnectionException($"That address will not work: {exception.Message}", exception);
        }
    }
}
