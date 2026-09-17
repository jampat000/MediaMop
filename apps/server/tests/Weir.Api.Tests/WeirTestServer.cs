using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;
using Weir.Api.Http;
using Weir.Core.Configuration;
using Weir.Host;

namespace Weir.Api.Tests;

/// <summary>The real server, built by <see cref="WeirServer"/>, on an in-memory test server with its own WEIR_HOME.</summary>
internal sealed class WeirTestServer : IAsyncDisposable
{
    private readonly WebApplication _app;

    private WeirTestServer(string home, WebApplication app)
    {
        Home = home;
        _app = app;
        Client = app.GetTestClient();
    }

    public string Home { get; }

    public HttpClient Client { get; }

    public IServiceProvider Services => _app.Services;

    public TestServer TestServer => _app.GetTestServer();

    /// <summary>Keep the home directory on dispose (for a second server on the same home).</summary>
    public bool KeepHome { get; set; }

    public static async Task<WeirTestServer> StartAsync(
        IEnumerable<(string Name, string Value)>? variables = null,
        bool signedIn = false,
        Action<string>? prepareHome = null,
        string? home = null,
        Action<IServiceCollection>? configureServices = null)
    {
        home ??= Path.Join(Path.GetTempPath(), "weir-api-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(home);
        prepareHome?.Invoke(home);
        var dictionary = new Dictionary<string, string>(StringComparer.Ordinal) { ["WEIR_HOME"] = home };
        foreach (var (name, value) in variables ?? [])
        {
            dictionary[name] = value.Replace("{home}", home, StringComparison.Ordinal);
        }

        var runtime = new RuntimeEnvironment(dictionary, OperatingSystem.IsWindows(), home, home);
        var app = WeirServer.Build([], runtime, builder =>
        {
            builder.WebHost.UseTestServer();
            if (signedIn)
            {
                builder.Services.AddSingleton<IOperatorAuthentication, SignedInAuthentication>();
            }

            configureServices?.Invoke(builder.Services);
        });
        await app.StartAsync();
        return new WeirTestServer(home, app);
    }

    /// <summary>Create a built-looking web app under <paramref name="home"/>/web.</summary>
    public static void WriteWebDist(string home)
    {
        var dist = Path.Join(home, "web");
        Directory.CreateDirectory(Path.Join(dist, "assets"));
        File.WriteAllText(Path.Join(dist, "index.html"), "<!doctype html><title>Weir</title>");
        File.WriteAllText(Path.Join(dist, "favicon.txt"), "icon");
        File.WriteAllText(Path.Join(dist, "assets", "app-abc123.js"), "console.log('plain');");
        File.WriteAllText(Path.Join(dist, "assets", "app-abc123.js.br"), "brotli-bytes");
        File.WriteAllText(Path.Join(dist, "assets", "app-abc123.js.gz"), "gzip-bytes");
        File.WriteAllText(Path.Join(dist, "assets", "font.woff2"), "font");
    }

    /// <summary>
    /// Replace the database file with a directory, so every new connection fails. The periodic tasks may
    /// hold the file open for a moment, which makes the delete fail or stay pending on Windows, so retry.
    /// </summary>
    public async Task BreakDatabaseAsync()
    {
        var dbPath = Path.Join(Home, "data", "weir.sqlite3");
        for (var attempt = 0; ; attempt++)
        {
            SqliteConnection.ClearAllPools();
            try
            {
                File.Delete(dbPath);
                File.Delete(dbPath + "-wal");
                File.Delete(dbPath + "-shm");
                Directory.CreateDirectory(dbPath);
                return;
            }
            catch (IOException) when (attempt < 50)
            {
                await Task.Delay(100);
            }
            catch (UnauthorizedAccessException) when (attempt < 50)
            {
                await Task.Delay(100);
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await _app.StopAsync();
        await _app.DisposeAsync();
        SqliteConnection.ClearAllPools();
        if (KeepHome)
        {
            return;
        }

        try
        {
            Directory.Delete(Home, recursive: true);
        }
        catch (IOException)
        {
            // A handle still closing on Windows; the temp folder is cleaned up eventually.
        }
    }

    private sealed class SignedInAuthentication : IOperatorAuthentication
    {
        public ValueTask<OperatorAuthenticationResult> AuthenticateAsync(HttpContext context) =>
            ValueTask.FromResult(OperatorAuthenticationResult.SignedIn);
    }
}
