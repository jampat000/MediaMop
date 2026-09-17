using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Weir.Api.Endpoints;
using Weir.Api.Http;
using Weir.Api.Web;
using Weir.Core.Configuration;
using Weir.Core.Metrics;
using Weir.Infrastructure;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Http;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Runtime;
using Weir.Infrastructure.Scheduling;
using Weir.Infrastructure.Settings;

namespace Weir.Api;

/// <summary>Registers the HTTP surface and builds its pipeline in the Python server's order.</summary>
public static class WeirApi
{
    public static IServiceCollection AddWeirApi(this IServiceCollection services, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddWeirPlatform(options);
        services.AddSingleton<ServerLifecycle>();
        services.AddSingleton(WebApp.Resolve(options.WebDist));
        services.AddSingleton<IOperatorAuthentication, SessionOperatorAuthentication>();
        services.AddSingleton<RouteTable>();
        services.TryAddSingleton<RuntimeMetricsStore>();
        services.AddSingleton<AuthService>();
        services.AddSingleton<AuthRateLimiters>();
        services.AddSingleton<ConfigurationBackups>();
        services.AddSingleton<UpdateFiles>();
        services.AddSingleton<IReleaseCatalogClient, GitHubReleaseCatalogClient>();
        services.AddSingleton<IExternalJsonPoster, ExternalJsonPoster>();
        services.AddSingleton<NotificationDispatcher>();
        services.AddWeirMediaManagers(options);

        // Scheduled work, hosted with the jobs (AddWeirJobs) by PeriodicTaskService.
        services.AddSingleton<SessionCleanupTask>();
        services.AddSingleton<LogRetentionTask>();
        services.AddSingleton<ConfigurationBackupTask>();
        services.AddSingleton<IPeriodicTask>(provider => provider.GetRequiredService<SessionCleanupTask>());
        services.AddSingleton<IPeriodicTask>(provider => provider.GetRequiredService<LogRetentionTask>());
        services.AddSingleton<IPeriodicTask>(provider => provider.GetRequiredService<ConfigurationBackupTask>());
        services.AddRouting();
        return services;
    }

    /// <summary>
    /// Python's stack, outermost first: the server's error response, forwarded headers (trusted proxies only), compressed
    /// assets, CORS (when origins are configured), the trusted-proxy scheme, HEAD-as-GET, the
    /// X-Requested-With check, request context, security headers, then routes, the static mount and the
    /// 404 handler.
    /// </summary>
    public static WebApplication UseWeirApi(this WebApplication app)
    {
        ArgumentNullException.ThrowIfNull(app);
        var options = app.Services.GetRequiredService<WeirOptions>();
        var webDist = app.Services.GetRequiredService<WebDist>();
        app.UseMiddleware<ServerErrorMiddleware>();
        app.UseTrustedForwardedHeaders(options);
        if (webDist.MountedAtStartup)
        {
            app.UseMiddleware<CompressedStaticAssetsMiddleware>();
        }

        if (options.CorsOrigins.Count > 0)
        {
            app.UseMiddleware<CorsMiddleware>();
        }

        app.UseMiddleware<TrustedProxySchemeMiddleware>();
        app.UseMiddleware<HeadMirrorsGetMiddleware>();
        app.UseMiddleware<XRequestedWithMiddleware>();
        app.UseMiddleware<RequestContextMiddleware>();
        app.UseMiddleware<SecurityHeadersMiddleware>();
        app.UseMiddleware<MethodNotAllowedBodyMiddleware>();
        app.UseRouting();
        // Static files run between routing and endpoints so matched routes win over files (Python's
        // routes are checked before its static mount), and the 404 handler runs only after both.
        // That ordering needs explicit UseEndpoints instead of top-level route registration.
#pragma warning disable ASP0014
        app.UseWebAppStaticFiles(webDist);
        app.UseEndpoints(endpoints =>
        {
            endpoints.MapSystemEndpoints();
            endpoints.MapMetricsEndpoint();
            endpoints.MapAuthEndpoints();
            endpoints.MapSuiteEndpoints();
            endpoints.MapReconciliationEndpoints();
            endpoints.MapMediaManagerEndpoints();
            endpoints.MapNotificationEndpoints();
            endpoints.MapActivityEndpoints();
            var routes = endpoints.ServiceProvider.GetRequiredService<RouteTable>();
            routes.Add("/", [HttpMethods.Get], "/");
            routes.Add("/index.html", [HttpMethods.Get], "/index.html");
            endpoints.MapWebAppIndex();
        });
#pragma warning restore ASP0014
        app.Run(WebApp.HandleUnmatchedAsync);
        return app;
    }
}
