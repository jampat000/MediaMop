using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Weir.Api.Endpoints;
using Weir.Api.Http;
using Weir.Api.Web;
using Weir.Core.Configuration;
using Weir.Core.Workers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api;

/// <summary>Registers the HTTP surface and builds its pipeline in the Python server's order.</summary>
public static class WeirApi
{
    public static IServiceCollection AddWeirApi(this IServiceCollection services, WeirOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        services.AddSingleton(options);
        services.AddSingleton(TimeProvider.System);
        services.AddSingleton<ServerLifecycle>();
        services.AddSingleton<WorkerHeartbeats>();
        services.AddSingleton(new SqliteDatabase(options.DbPath));
        services.AddSingleton(WebApp.Resolve(options.WebDist));
        services.AddSingleton<IOperatorAuthentication, SessionsNotPortedAuthentication>();
        services.AddRouting();
        return services;
    }

    /// <summary>
    /// Python's middleware, outermost first: compressed assets, request context, security headers,
    /// then routes, the static mount and the 404 handler.
    /// </summary>
    public static WebApplication UseWeirApi(this WebApplication app)
    {
        ArgumentNullException.ThrowIfNull(app);
        var webDist = app.Services.GetRequiredService<WebDist>();
        if (webDist.MountedAtStartup)
        {
            app.UseMiddleware<CompressedStaticAssetsMiddleware>();
        }

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
            endpoints.MapWebAppIndex();
        });
#pragma warning restore ASP0014
        app.Run(WebApp.HandleUnmatchedAsync);
        return app;
    }
}
