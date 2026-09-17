using System.Globalization;
using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Data.Sqlite;

namespace Weir.Api.Tests.Platform;

/// <summary>A browser-like client for the test server: keeps cookies, fetches CSRF tokens and signs in.</summary>
internal sealed class ApiTestClient
{
    public const string Secret = "api-tests-session-secret-0123456789abcdef";
    public const string AdminPassword = "test-password-strong";
    public const string ViewerPassword = "viewer-password-here";

    private readonly WeirTestServer _server;
    private readonly Dictionary<string, string> _cookies = new(StringComparer.Ordinal);

    public ApiTestClient(WeirTestServer server)
    {
        _server = server;
    }

    public IReadOnlyDictionary<string, string> Cookies => _cookies;

    /// <summary>A server with a session secret and no background workers.</summary>
    public static Task<WeirTestServer> StartServerAsync(params (string Name, string Value)[] variables) =>
        WeirTestServer.StartAsync([("WEIR_SESSION_SECRET", Secret), ("WEIR_REFINER_WORKER_COUNT", "0"), .. variables]);

    public async Task<HttpResponseMessage> SendAsync(HttpMethod method, string path, object? json = null, IReadOnlyDictionary<string, string>? headers = null, HttpContent? content = null)
    {
        using var request = new HttpRequestMessage(method, path);
        if (_cookies.Count > 0)
        {
            request.Headers.Add("Cookie", string.Join("; ", _cookies.Select(pair => $"{pair.Key}={pair.Value}")));
        }

        foreach (var (name, value) in headers ?? new Dictionary<string, string>())
        {
            request.Headers.TryAddWithoutValidation(name, value);
        }

        request.Content = content ?? (json is null ? null : JsonContent.Create(json, options: new JsonSerializerOptions(JsonSerializerDefaults.General)));
        var response = await _server.Client.SendAsync(request);
        if (response.Headers.TryGetValues("Set-Cookie", out var setCookies))
        {
            foreach (var header in setCookies)
            {
                var pair = header.Split(';')[0];
                var eq = pair.IndexOf('=', StringComparison.Ordinal);
                var name = pair[..eq];
                if (header.Contains("Max-Age=0", StringComparison.Ordinal))
                {
                    _cookies.Remove(name);
                }
                else
                {
                    _cookies[name] = pair[(eq + 1)..];
                }
            }
        }

        return response;
    }

    public Task<HttpResponseMessage> GetAsync(string path, IReadOnlyDictionary<string, string>? headers = null) => SendAsync(HttpMethod.Get, path, headers: headers);

    public Task<HttpResponseMessage> PostAsync(string path, object? json = null, IReadOnlyDictionary<string, string>? headers = null) => SendAsync(HttpMethod.Post, path, json, headers);

    public Task<HttpResponseMessage> PutAsync(string path, object? json = null, IReadOnlyDictionary<string, string>? headers = null) => SendAsync(HttpMethod.Put, path, json, headers);

    public async Task<string> CsrfAsync()
    {
        using var response = await GetAsync("/api/v1/auth/csrf");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return (await Json(response))["csrf_token"]!.GetValue<string>();
    }

    public async Task<HttpResponseMessage> LoginAsync(string username = "alice", string password = AdminPassword, bool trustedDevice = false) =>
        await PostAsync("/api/v1/auth/login", new { username, password, csrf_token = await CsrfAsync(), trusted_device = trustedDevice });

    public async Task SignInAsync(string username = "alice", string password = AdminPassword)
    {
        using var response = await LoginAsync(username, password);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    public void SetCookie(string name, string value) => _cookies[name] = value;

    public static async Task<JsonNode> Json(HttpResponseMessage response) => JsonNode.Parse(await response.Content.ReadAsStringAsync())!;

    public static async Task<string> Detail(HttpResponseMessage response) => (await Json(response))["detail"]!.GetValue<string>();

    public static string Header(HttpResponseMessage response, string name) =>
        response.Headers.TryGetValues(name, out var values) || response.Content.Headers.TryGetValues(name, out values)
            ? string.Join(", ", values)
            : string.Empty;
}

/// <summary>Direct database access for seeding and assertions, as the Python tests use their session factory.</summary>
internal static class TestDatabase
{
    public static string PathFor(WeirTestServer server) => System.IO.Path.Join(server.Home, "data", "weir.sqlite3");

    public static async Task<long> ScalarAsync(WeirTestServer server, string sql, params (string Name, object Value)[] parameters)
    {
        await using var connection = new SqliteConnection($"Data Source={PathFor(server)};Pooling=False");
        await connection.OpenAsync();
        await using var command = connection.CreateCommand();
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value);
        }

        return Convert.ToInt64(await command.ExecuteScalarAsync(), CultureInfo.InvariantCulture);
    }

    public static async Task ExecuteAsync(WeirTestServer server, string sql, params (string Name, object Value)[] parameters)
    {
        await using var connection = new SqliteConnection($"Data Source={PathFor(server)};Pooling=False");
        await connection.OpenAsync();
        await using var command = connection.CreateCommand();
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value);
        }

        await command.ExecuteNonQueryAsync();
    }

    /// <summary><c>seed_admin_user</c> / <c>seed_viewer_user</c>.</summary>
    public static Task SeedUserAsync(WeirTestServer server, string username, string password, string role) =>
        ExecuteAsync(
            server,
            "INSERT INTO users (username, password_hash, role, is_active) VALUES ($u, $h, $r, 1)",
            ("$u", username),
            ("$h", Core.Security.PasswordHasher.Hash(password)),
            ("$r", role));

    public static Task SeedAdminAsync(WeirTestServer server) => SeedUserAsync(server, "alice", ApiTestClient.AdminPassword, "admin");

    public static Task SeedViewerAsync(WeirTestServer server) => SeedUserAsync(server, "bob", ApiTestClient.ViewerPassword, "viewer");

    public static StringContent RawJson(string text, string contentType = "application/json") => new(text, Encoding.UTF8, contentType);
}
