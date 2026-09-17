using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Validation;
using Weir.Infrastructure.Refiner.DirectPlay;

namespace Weir.Api.Endpoints;

/// <summary>Choosing the devices the Direct Play badge answers for (port of <c>direct_play/api.py</c>, #467).</summary>
public static class RefinerDirectPlayEndpoints
{
    public static IEndpointRouteBuilder MapRefinerDirectPlayEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/refiner/direct-play/devices", GetDevicesAsync);
        endpoints.MapV1("PUT", "/refiner/direct-play/devices", PutDevicesAsync);
        return endpoints;
    }

    private static async Task<PyDict> BuildOutAsync(ApiRequest request)
    {
        var uow = await request.DbAsync().ConfigureAwait(false);
        var known = DeviceProfileLoader.Load(request.Options.WeirHome);
        var chosen = new HashSet<string>(await DirectPlayService.SelectedDeviceIdsAsync(uow).ConfigureAwait(false), StringComparer.Ordinal);
        var devices = known.Select(p => (PyJson)new PyDict()
            .Set("id", p.Id)
            .Set("name", p.Name)
            .Set("source", p.Source)
            .Set("note", p.Note)
            .Set("selected", chosen.Contains(p.Id)));
        return new PyDict()
            .Set("devices", new PyList(devices))
            .Set("customised", DirectPlayService.IsCustomised(request.Options.WeirHome));
    }

    private static async Task<ApiResult> GetDevicesAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await BuildOutAsync(request).ConfigureAwait(false));
    }

    private static async Task<ApiResult> PutDevicesAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var selected = model.StrList("selected", []);
        model.Finish(ExtraFields.Ignore);
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var uow = await request.DbAsync().ConfigureAwait(false);
        var known = DeviceProfileLoader.Load(request.Options.WeirHome);
        await DirectPlayService.SaveSelectedDeviceIdsAsync(uow, known, selected).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await BuildOutAsync(request).ConfigureAwait(false));
    }
}
