using System.Net;
using Weir.Api.Web;

namespace Weir.Api.Tests;

public sealed class WebAppTests
{
    private static readonly (string, string)[] WithWebDist = [("WEIR_WEB_DIST", "{home}/web")];

    [Fact]
    public async Task Index_is_served_with_no_cache_and_the_html_policy()
    {
        await using var server = await WeirTestServer.StartAsync(WithWebDist, prepareHome: WeirTestServer.WriteWebDist);

        foreach (var path in new[] { "/", "/index.html" })
        {
            using var response = await server.Client.GetAsync(path);
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            Assert.Equal("<!doctype html><title>Weir</title>", await response.Content.ReadAsStringAsync());
            Assert.Equal("text/html; charset=utf-8", response.Content.Headers.ContentType?.ToString());
            AssertNoCache(response);
            Assert.Equal("no-cache", Header(response, "Pragma"));
            Assert.Equal("0", Header(response, "Expires"));
            Assert.StartsWith("default-src 'self'; script-src 'self';", Header(response, "Content-Security-Policy"), StringComparison.Ordinal);
        }
    }

    [Fact]
    public async Task Browser_refreshes_on_client_routes_get_the_app_shell()
    {
        await using var server = await WeirTestServer.StartAsync(WithWebDist, prepareHome: WeirTestServer.WriteWebDist);

        using var byAccept = await Get(server, "/settings/media-managers", accept: "text/html,application/xhtml+xml");
        Assert.Equal(HttpStatusCode.OK, byAccept.StatusCode);
        AssertNoCache(byAccept);

        using var byFetchDest = await Get(server, "/activity", secFetchDest: "document");
        Assert.Equal(HttpStatusCode.OK, byFetchDest.StatusCode);
    }

    [Theory]
    [InlineData("/settings", null)]
    [InlineData("/api/v1/unknown", "text/html")]
    [InlineData("/health-check", "text/html")]
    [InlineData("/missing.png", "text/html")]
    [InlineData("/assets/missing.js", null)]
    public async Task Other_misses_are_fastapi_json_404s(string path, string? accept)
    {
        await using var server = await WeirTestServer.StartAsync(WithWebDist, prepareHome: WeirTestServer.WriteWebDist);

        using var response = await Get(server, path, accept);

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("{\"detail\":\"Not Found\"}", await response.Content.ReadAsStringAsync());
        Assert.Equal("application/json", response.Content.Headers.ContentType?.ToString());
    }

    [Fact]
    public async Task Without_a_web_dist_the_root_is_a_404_and_unknown_methods_are_404s()
    {
        await using var server = await WeirTestServer.StartAsync();

        using var root = await Get(server, "/", accept: "text/html");
        Assert.Equal(HttpStatusCode.NotFound, root.StatusCode);
        Assert.Equal("{\"detail\":\"Not Found\"}", await root.Content.ReadAsStringAsync());

        using var post = await server.Client.PostAsync("/somewhere", null);
        Assert.Equal(HttpStatusCode.NotFound, post.StatusCode);
    }

    [Fact]
    public async Task With_a_web_dist_unknown_methods_on_unrouted_paths_are_405s()
    {
        await using var server = await WeirTestServer.StartAsync(WithWebDist, prepareHome: WeirTestServer.WriteWebDist);

        using var post = await server.Client.PostAsync("/somewhere", null);

        Assert.Equal(HttpStatusCode.MethodNotAllowed, post.StatusCode);
        Assert.Equal("{\"detail\":\"Method Not Allowed\"}", await post.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Stale_upgrade_landings_redirect_to_settings()
    {
        await using var server = await WeirTestServer.StartAsync();

        using var response = await server.Client.GetAsync("/api/v1/system/Upgrade-Now");

        Assert.Equal(HttpStatusCode.SeeOther, response.StatusCode);
        Assert.Equal("/settings", response.Headers.Location?.ToString());
    }

    [Fact]
    public async Task Other_files_come_from_the_dist_with_a_text_charset()
    {
        await using var server = await WeirTestServer.StartAsync(WithWebDist, prepareHome: WeirTestServer.WriteWebDist);

        using var response = await server.Client.GetAsync("/favicon.txt");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("icon", await response.Content.ReadAsStringAsync());
        Assert.Equal("text/plain; charset=utf-8", response.Content.Headers.ContentType?.ToString());
        Assert.Equal("nosniff", Header(response, "X-Content-Type-Options"));
    }

    [Fact]
    public async Task Assets_are_immutable_and_negotiate_precompressed_variants()
    {
        await using var server = await WeirTestServer.StartAsync(WithWebDist, prepareHome: WeirTestServer.WriteWebDist);

        using var brotli = await Get(server, "/assets/app-abc123.js", acceptEncoding: "gzip, br");
        Assert.Equal(HttpStatusCode.OK, brotli.StatusCode);
        Assert.Equal("brotli-bytes", await brotli.Content.ReadAsStringAsync());
        Assert.Equal("br", Header(brotli, "Content-Encoding"));
        Assert.Equal("public, max-age=31536000, immutable", Header(brotli, "Cache-Control"));
        Assert.Equal("Accept-Encoding", Header(brotli, "Vary"));
        Assert.Equal("application/javascript", brotli.Content.Headers.ContentType?.ToString());
        // Outside the header middleware, as in Python.
        Assert.Equal(string.Empty, Header(brotli, "X-Request-ID"));
        Assert.Equal(string.Empty, Header(brotli, "Content-Security-Policy"));

        using var gzip = await Get(server, "/assets/app-abc123.js", acceptEncoding: "br;q=0, gzip");
        Assert.Equal("gzip-bytes", await gzip.Content.ReadAsStringAsync());
        Assert.Equal("gzip", Header(gzip, "Content-Encoding"));

        using var plain = await Get(server, "/assets/app-abc123.js");
        Assert.Equal("console.log('plain');", await plain.Content.ReadAsStringAsync());
        Assert.Equal(string.Empty, Header(plain, "Content-Encoding"));
        Assert.NotEqual(Header(brotli, "ETag"), Header(plain, "ETag"));

        using var font = await Get(server, "/assets/font.woff2", acceptEncoding: "br");
        Assert.Equal("font", await font.Content.ReadAsStringAsync());
        Assert.Equal(string.Empty, Header(font, "Content-Encoding"));
    }

    [Fact]
    public async Task Asset_etags_answer_304()
    {
        await using var server = await WeirTestServer.StartAsync(WithWebDist, prepareHome: WeirTestServer.WriteWebDist);
        using var first = await Get(server, "/assets/app-abc123.js");
        var etag = Header(first, "ETag");

        using var request = new HttpRequestMessage(HttpMethod.Get, "/assets/app-abc123.js");
        request.Headers.TryAddWithoutValidation("If-None-Match", etag);
        using var second = await server.Client.SendAsync(request);

        Assert.Equal(HttpStatusCode.NotModified, second.StatusCode);
        Assert.Equal("public, max-age=31536000, immutable", Header(second, "Cache-Control"));
    }

    [Theory]
    [InlineData("gzip, br", "br", true)]
    [InlineData("gzip;q=0", "gzip", false)]
    [InlineData("*", "br", true)]
    [InlineData("*;q=0", "br", false)]
    [InlineData("br;q=0, *", "br", false)]
    [InlineData("identity", "gzip", false)]
    [InlineData("gzip;q=bad", "gzip", false)]
    public void Accept_encoding_negotiation(string header, string encoding, bool expected) =>
        Assert.Equal(expected, CompressedStaticAssetsMiddleware.AcceptsEncoding(header, encoding));

    [Theory]
    [InlineData("/assets/../index.html")]
    [InlineData("/assets/./app.js")]
    [InlineData("/other/app.js")]
    [InlineData("/assets/")]
    public void Asset_paths_stay_inside_assets(string urlPath) =>
        Assert.Null(CompressedStaticAssetsMiddleware.AssetPath(Path.GetTempPath(), urlPath));

    [Theory]
    [InlineData("/settings", "")]
    [InlineData("/a/b.png", ".png")]
    [InlineData("/.well-known", "")]
    [InlineData("/file.", "")]
    [InlineData("/archive.tar.gz", ".gz")]
    [InlineData("/dir.d/", ".d")]
    public void Path_suffix_matches_pathlib(string path, string expected) => Assert.Equal(expected, WebApp.PathSuffix(path));

    private static async Task<HttpResponseMessage> Get(
        WeirTestServer server,
        string path,
        string? accept = null,
        string? secFetchDest = null,
        string? acceptEncoding = null)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, path);
        if (accept is not null)
        {
            request.Headers.TryAddWithoutValidation("Accept", accept);
        }

        if (secFetchDest is not null)
        {
            request.Headers.TryAddWithoutValidation("Sec-Fetch-Dest", secFetchDest);
        }

        if (acceptEncoding is not null)
        {
            request.Headers.TryAddWithoutValidation(HeaderNames.AcceptEncoding, acceptEncoding);
        }

        return await server.Client.SendAsync(request);
    }

    /// <summary>HttpClient re-orders Cache-Control directives, so compare them as a set.</summary>
    private static void AssertNoCache(HttpResponseMessage response)
    {
        var cacheControl = response.Headers.CacheControl;
        Assert.NotNull(cacheControl);
        Assert.True(cacheControl.NoCache && cacheControl.NoStore && cacheControl.MustRevalidate);
        Assert.False(cacheControl.Private || cacheControl.Public);
        Assert.Null(cacheControl.MaxAge);
    }

    private static string Header(HttpResponseMessage response, string name) =>
        response.Headers.TryGetValues(name, out var values) || response.Content.Headers.TryGetValues(name, out values)
            ? string.Join(", ", values)
            : string.Empty;

    private static class HeaderNames
    {
        public const string AcceptEncoding = "Accept-Encoding";
    }
}
