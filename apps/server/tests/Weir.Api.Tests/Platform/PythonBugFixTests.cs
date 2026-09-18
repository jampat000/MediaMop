using System.Net;
using System.Text;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using static Weir.Api.Tests.Platform.ApiTestClient;

namespace Weir.Api.Tests.Platform;

/// <summary>
/// Deliberate deviations from the Python backend: bugs the contract suite found (#528, #529, #535, #536),
/// fixed in the .NET server instead of ported.
/// </summary>
public sealed class PythonBugFixTests
{
    /// <summary>A login request from a chosen TCP peer, with extra headers.</summary>
    private static async Task<HttpContext> LoginFromPeerAsync(WeirTestServer server, string peer, IReadOnlyDictionary<string, string> headers)
    {
        var csrf = await new ApiTestClient(server).CsrfAsync();
        var body = Encoding.UTF8.GetBytes($"{{\"username\":\"alice\",\"password\":\"wrong-password\",\"csrf_token\":\"{csrf}\"}}");
        return await server.TestServer.SendAsync(context =>
        {
            context.Connection.RemoteIpAddress = IPAddress.Parse(peer);
            context.Request.Method = "POST";
            context.Request.Path = "/api/v1/auth/login";
            context.Request.Headers.ContentType = "application/json";
            foreach (var (name, value) in headers)
            {
                context.Request.Headers[name] = value;
            }

            context.Request.Body = new MemoryStream(body);
        });
    }

    private static async Task<HttpContext> SignInFromPeerAsync(WeirTestServer server, string peer, IReadOnlyDictionary<string, string> headers)
    {
        var csrf = await new ApiTestClient(server).CsrfAsync();
        var body = Encoding.UTF8.GetBytes($"{{\"username\":\"alice\",\"password\":\"{AdminPassword}\",\"csrf_token\":\"{csrf}\"}}");
        return await server.TestServer.SendAsync(context =>
        {
            context.Connection.RemoteIpAddress = IPAddress.Parse(peer);
            context.Request.Method = "POST";
            context.Request.Path = "/api/v1/auth/login";
            context.Request.Headers.ContentType = "application/json";
            foreach (var (name, value) in headers)
            {
                context.Request.Headers[name] = value;
            }

            context.Request.Body = new MemoryStream(body);
        });
    }

    [Fact]
    public async Task Issue_528_forwarded_headers_from_an_untrusted_peer_are_ignored()
    {
        await using var server = await StartServerAsync(("WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS", "1"));
        await TestDatabase.SeedAdminAsync(server);

        // A spoofed X-Forwarded-Proto must not make the cookie Secure (or change the scheme).
        var signIn = await SignInFromPeerAsync(server, "192.0.2.50", new Dictionary<string, string> { ["X-Forwarded-Proto"] = "https", ["X-Forwarded-For"] = "203.0.113.1" });
        Assert.Equal(200, signIn.Response.StatusCode);
        Assert.DoesNotContain("Secure", signIn.Response.Headers.SetCookie.ToString(), StringComparison.Ordinal);

        // A spoofed X-Forwarded-For must not give each attempt a fresh rate-limit bucket.
        var first = await LoginFromPeerAsync(server, "192.0.2.60", new Dictionary<string, string> { ["X-Forwarded-For"] = "203.0.113.2" });
        Assert.Equal(401, first.Response.StatusCode);
        var second = await LoginFromPeerAsync(server, "192.0.2.60", new Dictionary<string, string> { ["X-Forwarded-For"] = "203.0.113.3" });
        Assert.Equal(429, second.Response.StatusCode);
    }

    [Fact]
    public async Task Issue_528_forwarded_headers_from_a_trusted_proxy_are_honoured()
    {
        await using var server = await StartServerAsync(("WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS", "1"), ("WEIR_TRUSTED_PROXY_IPS", "10.0.0.0/24"));
        await TestDatabase.SeedAdminAsync(server);

        var signIn = await SignInFromPeerAsync(server, "10.0.0.1", new Dictionary<string, string> { ["X-Forwarded-Proto"] = "https", ["X-Forwarded-For"] = "203.0.113.1" });
        Assert.Equal(200, signIn.Response.StatusCode);
        Assert.EndsWith("; Secure", signIn.Response.Headers.SetCookie.ToString(), StringComparison.Ordinal);

        var first = await LoginFromPeerAsync(server, "10.0.0.1", new Dictionary<string, string> { ["X-Forwarded-For"] = "203.0.113.2" });
        Assert.Equal(401, first.Response.StatusCode);
        var second = await LoginFromPeerAsync(server, "10.0.0.1", new Dictionary<string, string> { ["X-Forwarded-For"] = "203.0.113.3" });
        Assert.Equal(401, second.Response.StatusCode);
        var repeat = await LoginFromPeerAsync(server, "10.0.0.1", new Dictionary<string, string> { ["X-Forwarded-For"] = "203.0.113.3" });
        Assert.Equal(429, repeat.Response.StatusCode);
    }

    [Fact]
    public async Task Issue_529_an_expired_session_is_revoked_and_answers_401()
    {
        await using var server = await StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        await TestDatabase.ExecuteAsync(server, "UPDATE user_sessions SET last_seen_at = '2000-01-01 00:00:00.000000', created_at = '2000-01-01 00:00:00.000000', absolute_expires_at = '2000-02-01 00:00:00.000000'");

        using var me = await client.GetAsync("/api/v1/auth/me");
        Assert.Equal(HttpStatusCode.Unauthorized, me.StatusCode);
        Assert.Equal("Not authenticated.", await Detail(me));
        Assert.Equal(1, await TestDatabase.ScalarAsync(server, "SELECT count(*) FROM user_sessions WHERE revoked_at IS NOT NULL"));
    }

    [Fact]
    public async Task Issue_535_api_paths_never_fall_back_to_the_web_app()
    {
        await using var withDist = await WeirTestServer.StartAsync(
            [("WEIR_SESSION_SECRET", Secret), ("WEIR_PROCESSING_WORKER_COUNT", "0"), ("WEIR_WEB_DIST", "{home}/web")],
            prepareHome: WeirTestServer.WriteWebDist);
        var client = new ApiTestClient(withDist);
        var html = new Dictionary<string, string> { ["Accept"] = "text/html,application/xhtml+xml" };

        foreach (var method in new[] { HttpMethod.Get, HttpMethod.Head, HttpMethod.Put })
        {
            using var wrongMethod = await client.SendAsync(method, "/api/v1/auth/login", headers: html);
            Assert.Equal(HttpStatusCode.MethodNotAllowed, wrongMethod.StatusCode);
            Assert.Equal("POST", Header(wrongMethod, "Allow"));
            if (method != HttpMethod.Head)
            {
                Assert.Equal("{\"detail\":\"Method Not Allowed\"}", await wrongMethod.Content.ReadAsStringAsync());
                Assert.Equal("application/json", wrongMethod.Content.Headers.ContentType?.ToString());
            }
        }

        foreach (var method in new[] { HttpMethod.Get, HttpMethod.Post })
        {
            using var unknown = await client.SendAsync(method, "/api/v1/nope", headers: html);
            Assert.Equal(HttpStatusCode.NotFound, unknown.StatusCode);
            Assert.Equal("{\"detail\":\"Not Found\"}", await unknown.Content.ReadAsStringAsync());
        }

        using var clientRoute = await client.GetAsync("/settings/general", html);
        Assert.Equal(HttpStatusCode.OK, clientRoute.StatusCode);
        Assert.Equal("<!doctype html><title>Weir</title>", await clientRoute.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Issue_536_logs_with_invalid_utf8_are_read_and_settings_still_save()
    {
        await using var server = await StartServerAsync();
        await TestDatabase.SeedAdminAsync(server);
        var client = new ApiTestClient(server);
        await client.SignInAsync();
        var logFile = server.Services.GetRequiredService<Infrastructure.Logging.WeirLogFile>();
        await using (var stream = new FileStream(logFile.Path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete))
        {
            var line = Encoding.UTF8.GetBytes("{\"timestamp\":\"2026-05-09T10:00:00Z\",\"level\":\"ERROR\",\"logger\":\"weir\",\"message\":\"bad byte X here\"}\n");
            line[Array.IndexOf(line, (byte)'X')] = 0xFF;
            await stream.WriteAsync(line);
        }

        using var logs = await client.GetAsync("/api/v1/suite/logs?search=bad%20byte");
        Assert.Equal(HttpStatusCode.OK, logs.StatusCode);
        Assert.Equal("bad byte � here", (await Json(logs))["items"]![0]!["message"]!.GetValue<string>());

        using var put = await client.PutAsync("/api/v1/suite/settings", new { csrf_token = await client.CsrfAsync(), product_display_name = "Still Saves", app_timezone = "UTC", log_retention_days = 7 });
        Assert.Equal(HttpStatusCode.OK, put.StatusCode);
        Assert.Equal("Still Saves", (await Json(put))["product_display_name"]!.GetValue<string>());
        Assert.Equal(7, await TestDatabase.ScalarAsync(server, "SELECT log_retention_days FROM suite_settings WHERE id = 1"));
    }
}
