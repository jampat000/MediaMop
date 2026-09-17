using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Api.Http;
using Weir.Core.Activity;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.MediaManagers;
using Weir.Core.Time;
using Weir.Core.Validation;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api.Endpoints;

/// <summary>
/// Media manager connections and capabilities, the intake webhook and hand-off status, and system reconciliation
/// (ports of <c>media_managers.connections_api</c>, <c>media_managers.intake_api</c> and <c>reconciliation.router</c>).
/// </summary>
public static class MediaManagerEndpoints
{
    private const string InvalidCsrf = "Invalid or expired CSRF token.";
    private const string NoSuchConnection = "That media manager connection does not exist.";

    private static readonly TimeSpan TestTimeout = TimeSpan.FromSeconds(15);

    /// <summary>Where each kind answers a liveness check.</summary>
    private static readonly Dictionary<string, string> HealthPaths = new(StringComparer.Ordinal)
    {
        ["radarr"] = "/api/v3/system/status",
        ["sonarr"] = "/api/v3/system/status",
        ["deluno"] = "/api/integrations/external/health",
        ["native"] = "/api/integrations/external/health",
    };

    /// <summary><c>weir.platform.reconciliation.router</c> (registered after local browse, as in Python).</summary>
    public static IEndpointRouteBuilder MapReconciliationEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/system/reconciliation", GetReconciliationAsync);
        endpoints.MapV1("POST", "/system/reconciliation/repair", PostReconciliationRepairAsync);
        return endpoints;
    }

    /// <summary>The intake router, then the connections router, in Python's order.</summary>
    public static IEndpointRouteBuilder MapMediaManagerEndpoints(this IEndpointRouteBuilder endpoints)
    {
        // weir.platform.media_managers.intake_api
        endpoints.MapV1("POST", "/intake/webhook/{source_key}", PostWebhookAsync);
        endpoints.MapV1("GET", "/intake/capabilities", GetIntakeCapabilitiesAsync);
        endpoints.MapV1("GET", "/intake/handoffs/{source_key}/{handoff_id}", GetHandoffAsync);
        endpoints.MapV1("DELETE", "/intake/handoffs/{source_key}/{handoff_id}", DeleteHandoffAsync);

        // weir.platform.media_managers.connections_api
        endpoints.MapV1("GET", "/media-managers/connections", ListConnectionsAsync);
        endpoints.MapV1("POST", "/media-managers/connections", CreateConnectionAsync);
        endpoints.MapV1("GET", "/media-managers/capabilities", GetCapabilitiesAsync);
        endpoints.MapV1("GET", "/media-managers/connections/{connection_id}", GetConnectionAsync);
        endpoints.MapV1("PUT", "/media-managers/connections/{connection_id}", UpdateConnectionAsync);
        endpoints.MapV1("DELETE", "/media-managers/connections/{connection_id}", DeleteConnectionAsync);
        endpoints.MapV1("POST", "/media-managers/connections/{connection_id}/webhook-secret", PostWebhookSecretAsync);
        endpoints.MapV1("PUT", "/media-managers/connections/{connection_id}/lanes/{lane}", PutLaneAsync);
        endpoints.MapV1("POST", "/media-managers/connections/{connection_id}/test", PostConnectionTestAsync);
        return endpoints;
    }

    // --- connections ---------------------------------------------------------------------------

    /// <summary><c>_verify_csrf</c>.</summary>
    private static void VerifyCsrf(ApiRequest request, string? token)
    {
        request.ValidateBrowserPostOrigin();
        var secret = request.RequireSessionSecret();
        if (!request.VerifyCsrf(secret, token, allowAnonymous: false))
        {
            throw new ApiException(StatusCodes.Status400BadRequest, InvalidCsrf);
        }
    }

    /// <summary>An <c>int = Path(ge=1)</c> parameter.</summary>
    private static long ConnectionId(ApiRequest request, ValidationIssues issues)
    {
        var raw = request.RouteValue("connection_id") ?? string.Empty;
        return PydanticRules.TryInt(new PyStr(raw), ["path", "connection_id"], 1, null, issues, out var value)
            ? value > long.MaxValue ? long.MaxValue : (long)value
            : 0;
    }

    private static async Task<MediaManagerConnectionRecord> RequireConnectionAsync(UnitOfWork uow, long connectionId) =>
        await MediaManagerConnectionStore.GetAsync(uow, connectionId).ConfigureAwait(false)
        ?? throw new ApiException(StatusCodes.Status404NotFound, NoSuchConnection);

    private static MediaManagerConnectionService Connections(ApiRequest request) => request.Service<MediaManagerConnectionService>();

    private static async Task<ApiResult> ListConnectionsAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var rows = await MediaManagerConnectionStore.ListAsync(uow).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyList(rows.Select(row => (PyJson)row.ToOut())));
    }

    /// <summary>A <c>str</c> field with a default: absent means the default, present must be a string.</summary>
    private static string StrWithDefault(BodyModel model, PyJson? body, string name, string defaultValue, int? maxLength) =>
        body is PyDict dict && dict.ContainsKey(name) ? model.Str(name, maxLength: maxLength) : defaultValue;

    private static async Task<ApiResult> CreateConnectionAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var kind = model.Literal("kind", MediaManagerKinds.All);
        var name = model.Str("name", minLength: 1, maxLength: 200);
        var enabled = model.Bool("enabled", defaultValue: true);
        var baseUrl = StrWithDefault(model, body, "base_url", string.Empty, 2000);
        var apiKey = StrWithDefault(model, body, "api_key", string.Empty, 2000);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        VerifyCsrf(request, csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        long id;
        try
        {
            id = await Connections(request).CreateAsync(uow, kind, name, baseUrl, apiKey.Length > 0 ? apiKey : null, enabled).ConfigureAwait(false);
        }
        catch (MediaManagerConnectionException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        var row = await RequireConnectionAsync(uow, id).ConfigureAwait(false);
        return new JsonApiResult(StatusCodes.Status201Created, row.ToOut());
    }

    private static async Task<ApiResult> GetCapabilitiesAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var output = new PyList();
        foreach (var described in await Connections(request).DescribeConnectionsAsync(uow, request.Context.RequestAborted).ConfigureAwait(false))
        {
            var capabilities = described.Capabilities;
            output.Items.Add(new PyDict()
                .Set("connection_id", described.Connection.ConnectionId ?? 0)
                .Set("kind", described.Connection.Kind)
                .Set("name", described.Connection.Name)
                .Set("label", described.Connection.Label)
                .Set("media_scopes", new PyList(capabilities.Scopes.Order(StringComparer.Ordinal).Select(scope => (PyJson)new PyStr(scope))))
                .Set("reports_import_queue", capabilities.ReportsQueue)
                .Set("reports_library_truth", capabilities.ReportsLibraryTruth)
                .Set("reachable", described.Status == SignalStatus.Reported)
                .Set("library_roots", new PyList(described.LibraryRoots.Select(root => (PyJson)new PyStr(root))))
                .Set("summary", capabilities.Summary)
                .Set("detail", described.Detail));
        }

        return ApiRoutes.Ok(output);
    }

    private static async Task<ApiResult> GetConnectionAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        issues.ThrowIfAny();
        var uow = await request.DbAsync().ConfigureAwait(false);
        return ApiRoutes.Ok((await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false)).ToOut());
    }

    private static async Task<ApiResult> UpdateConnectionAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var name = model.OptionalStr("name", minLength: 1, maxLength: 200);
        var enabled = model.OptionalBool("enabled");
        var baseUrl = model.OptionalStr("base_url", maxLength: 2000);
        var apiKey = model.OptionalStr("api_key", maxLength: 2000);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        VerifyCsrf(request, csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        try
        {
            await Connections(request).UpdateAsync(uow, row, name, baseUrl, apiKey, enabled).ConfigureAwait(false);
        }
        catch (MediaManagerConnectionException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok((await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false)).ToOut());
    }

    private static async Task<ApiResult> DeleteConnectionAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        VerifyCsrf(request, csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        await MediaManagerConnectionStore.DeleteAsync(uow, connectionId).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return new CustomApiResult(context =>
        {
            PyResponses.NoContentJson(context);
            return Task.CompletedTask;
        });
    }

    private static async Task<ApiResult> PostWebhookSecretAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        VerifyCsrf(request, csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        var plaintext = await Connections(request).RotateWebhookSecretAsync(uow, row).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("connection_id", row.Id)
            .Set("webhook_secret", plaintext)
            .Set("webhook_url_path", row.WebhookUrlPath)
            .Set("header_name", "X-Webhook-Secret"));
    }

    private static async Task<ApiResult> PutLaneAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        PydanticRules.TryLiteral(new PyStr(request.RouteValue("lane") ?? string.Empty), ["path", "lane"], MediaManagerKinds.SearchLanes, issues, out var lane);
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var enabled = model.Bool("enabled", defaultValue: false, required: true);
        var maxItems = model.Number("max_items_per_run", 0, required: true, ge: 1, le: 1000);
        var retryDelay = model.Number("retry_delay_minutes", 0, required: true, ge: 1, le: 525600);
        var scheduleEnabled = model.Bool("schedule_enabled", defaultValue: false, required: true);
        var scheduleDays = model.Str("schedule_days", maxLength: 2000);
        var scheduleStart = model.Str("schedule_start", maxLength: 5);
        var scheduleEnd = model.Str("schedule_end", maxLength: 5);
        var interval = model.Number("schedule_interval_seconds", 0, required: true, ge: 60, le: 604800);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        VerifyCsrf(request, csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        string days;
        try
        {
            days = ScheduleCsv.ValidateScheduleDaysCsv(scheduleDays);
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        // Python lets a ValueError from normalize_hhmm escape as a 500; kept.
        var saved = await MediaManagerConnectionStore.SaveLaneAsync(uow, new MediaManagerSearchLaneRecord(
            0,
            connectionId,
            lane,
            enabled,
            maxItems,
            retryDelay,
            scheduleEnabled,
            days,
            ScheduleCsv.NormalizeHhmm(scheduleStart, "00:00"),
            ScheduleCsv.NormalizeHhmm(scheduleEnd, "23:59"),
            interval)).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(saved.ToOut());
    }

    /// <summary><c>_probe</c>: ask the manager whether it is there, and say what happened in plain words.</summary>
    private static async Task<(bool Ok, string Detail)> ProbeAsync(ApiRequest request, string name, string kind, string baseUrl, string? apiKey)
    {
        var path = HealthPaths.GetValueOrDefault(kind, "/api/integrations/external/health");
        try
        {
            var client = new MediaManagerHttpClient(baseUrl, apiKey ?? string.Empty, request.Service<IManagerHttpHandlerFactory>(), TestTimeout);
            await client.HealthOkAsync(path, request.Context.RequestAborted).ConfigureAwait(false);
        }
        catch (MediaManagerHttpException exception)
        {
            var detail = exception.Message;
            if (detail.Contains("HTTP 401", StringComparison.Ordinal) || detail.Contains("HTTP 403", StringComparison.Ordinal))
            {
                return (false, $"Weir reached {name}, but the API key was refused. Check the key and save it again.");
            }

            return (false, $"Weir reached {name} but did not get the answer it expected. Check the address points at the app itself, not a page inside it.");
        }
        catch (MediaManagerUnreachableException)
        {
            return (false, $"Weir could not reach {name} at {baseUrl}. Check the address is right, and that the app is running and reachable from this machine.");
        }

        return (true, $"Connected. Weir can reach {name}.");
    }

    private static async Task<ApiResult> PostConnectionTestAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var connectionId = ConnectionId(request, issues);
        var model = new BodyModel(body, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Forbid);
        issues.ThrowIfAny();

        VerifyCsrf(request, csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var row = await RequireConnectionAsync(uow, connectionId).ConfigureAwait(false);
        var checkedAt = PyDateTime.UtcNow(request.Time);

        bool ok;
        string detail;
        if (PyStrings.Strip(row.BaseUrl).Length == 0)
        {
            (ok, detail) = (false, "Add the address where this app can be reached, then test again.");
        }
        else
        {
            var apiKey = string.IsNullOrEmpty(row.ApiKeyCiphertext) ? null : Connections(request).Cipher.Decrypt(row.ApiKeyCiphertext);
            (ok, detail) = await ProbeAsync(request, row.Name, row.Kind, row.BaseUrl, apiKey).ConfigureAwait(false);
        }

        // The probe can take seconds and the connection may be removed meanwhile, so the write is conditional.
        if (await MediaManagerConnectionStore.RecordTestResultAsync(uow, connectionId, ok, checkedAt, detail).ConfigureAwait(false) == 0)
        {
            await uow.RollbackAsync().ConfigureAwait(false);
            throw new ApiException(StatusCodes.Status404NotFound, "That media manager connection was removed while its connection test was running.");
        }

        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("connection_id", row.Id)
            .Set("ok", ok)
            .Set("detail", detail)
            .Set("checked_at", checkedAt.PydanticJson()));
    }

    // --- intake --------------------------------------------------------------------------------

    private static MediaManagerIntake Intake(ApiRequest request) => request.Service<MediaManagerIntake>();

    private static async Task<T> RefusalsAsApiErrors<T>(Func<Task<T>> work)
    {
        try
        {
            return await work().ConfigureAwait(false);
        }
        catch (IntakeRefusedException exception)
        {
            throw new ApiException(exception.StatusCode, exception.Message);
        }
    }

    private static async Task<ApiResult> PostWebhookAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        var sourceKey = request.RouteValue("source_key") ?? string.Empty;
        var presented = request.FirstHeader("X-Webhook-Secret");
        var issues = new ValidationIssues();
        PyDict payload = new();
        if (body is null or PyNull)
        {
            issues.Add(PydanticRules.Missing(["body"], PyNull.Instance));
        }
        else
        {
            PydanticRules.TryDict(body, ["body"], issues, out payload);
        }

        issues.ThrowIfAny();

        var dialect = ImportEvents.DialectForSource(sourceKey)
            ?? throw new ApiException(StatusCodes.Status404NotFound, IntakeRules.UnknownSourceDetail(sourceKey));
        var uow = await request.DbAsync().ConfigureAwait(false);
        await RefusalsAsApiErrors(async () =>
        {
            await Intake(request).AuthoriseAsync(uow, dialect.Key, presented).ConfigureAwait(false);
            return 0;
        }).ConfigureAwait(false);

        var importEvent = dialect.Normalize(payload);
        if (importEvent is null)
        {
            return ApiRoutes.Ok(new PyDict().Set("status", "ignored").Set("source", dialect.Key));
        }

        if (importEvent.EventKind == MediaManagerImportEvent.Imported)
        {
            return ApiRoutes.Ok(new PyDict().Set("status", "ignored").Set("source", dialect.Key).Set("event", importEvent.EventKind));
        }

        var enqueued = await RefusalsAsApiErrors(() => Intake(request).EnqueueRefineAsync(uow, importEvent)).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict()
            .Set("status", "ok")
            .Set("source", dialect.Key)
            .Set("event", importEvent.EventKind)
            .Set("media_scope", importEvent.MediaScope)
            .Set("enqueued", enqueued));
    }

    /// <summary><c>_source</c>: the dialect key, or 404.</summary>
    private static string Source(string sourceKey) =>
        ImportEvents.DialectForSource(sourceKey)?.Key
        ?? throw new ApiException(StatusCodes.Status404NotFound, IntakeRules.UnknownSourceShortDetail(sourceKey));

    private static async Task<ApiResult> GetIntakeCapabilitiesAsync(ApiRequest request)
    {
        var presented = request.FirstHeader("X-Webhook-Secret");
        var uow = await request.DbAsync().ConfigureAwait(false);
        await RefusalsAsApiErrors(async () =>
        {
            await Intake(request).RequireSecretAsync(uow, presented, null).ConfigureAwait(false);
            return 0;
        }).ConfigureAwait(false);
        return ApiRoutes.Ok(new PyDict().Set("capabilities", new PyList(IntakeRules.HandoffCapabilities.Select(c => (PyJson)new PyStr(c)))));
    }

    private static async Task<(UnitOfWork Uow, string Key, HandoffLedgerRow Row)> RequireHandoffAsync(ApiRequest request)
    {
        var sourceKey = request.RouteValue("source_key") ?? string.Empty;
        var handoffId = request.RouteValue("handoff_id") ?? string.Empty;
        var presented = request.FirstHeader("X-Webhook-Secret");
        var key = Source(sourceKey);
        var uow = await request.DbAsync().ConfigureAwait(false);
        await RefusalsAsApiErrors(async () =>
        {
            await Intake(request).RequireSecretAsync(uow, presented, key).ConfigureAwait(false);
            return 0;
        }).ConfigureAwait(false);
        var row = await HandoffLedgerStore.FindAsync(uow, key, handoffId).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status404NotFound, IntakeRules.NeverReceivedDetail);
        return (uow, key, row);
    }

    private static async Task<ApiResult> GetHandoffAsync(ApiRequest request)
    {
        var (uow, _, row) = await RequireHandoffAsync(request).ConfigureAwait(false);
        var answer = await Intake(request).Ledger.CurrentStatusAsync(uow, row).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(answer.AsJson());
    }

    private static async Task<ApiResult> DeleteHandoffAsync(ApiRequest request)
    {
        var (uow, key, row) = await RequireHandoffAsync(request).ConfigureAwait(false);
        var intake = Intake(request);
        var (cancelled, sentence) = await intake.Ledger.CancelAsync(uow, intake.Jobs, row).ConfigureAwait(false);
        if (!cancelled)
        {
            await uow.RollbackAsync().ConfigureAwait(false);
            throw new ApiException(StatusCodes.Status409Conflict, sentence);
        }

        await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
            ActivityEventTypes.RefinerHandoffCancelled,
            "refiner",
            IntakeRules.CancelledTitle(key, row.RelativePath, OperatingSystem.IsWindows()),
            IntakeRules.CancelledDetail(key, row.HandoffId, row.RelativePath, row.LibraryId, sentence))).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return new CustomApiResult(context =>
        {
            context.Response.StatusCode = StatusCodes.Status204NoContent;
            return Task.CompletedTask;
        });
    }

    // --- reconciliation ------------------------------------------------------------------------

    private static async Task<ApiResult> GetReconciliationAsync(ApiRequest request)
    {
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var uow = await request.DbAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(await ReconciliationService.BuildReportAsync(uow).ConfigureAwait(false));
    }

    /// <summary>
    /// <c>post_reconciliation_repair</c>. Deliberate fix (#527): Python accepted this with only the session cookie; it now
    /// requires the browser origin check and a session-bound <c>csrf_token</c> like every other operator POST, answering
    /// 403 for a bad origin and 400 <c>Invalid or expired CSRF token.</c> for a missing or wrong token.
    /// </summary>
    private static async Task<ApiResult> PostReconciliationRepairAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var action = model.Str("action", minLength: 1, maxLength: 100);
        var dbId = model.OptionalInt("db_id", ge: 1);
        var path = model.OptionalStr("path", maxLength: 2000);
        var confirm = model.Bool("confirm", defaultValue: false);
        var csrfToken = model.OptionalStr("csrf_token");
        model.Finish(ExtraFields.Ignore);
        issues.ThrowIfAny();

        VerifyCsrf(request, csrfToken);
        var uow = await request.DbAsync().ConfigureAwait(false);
        PyDict result;
        try
        {
            result = await ReconciliationService.RepairAsync(uow, action, dbId, path, confirm).ConfigureAwait(false);
        }
        catch (PyValueErrorException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
        }

        var applied = result.Get("applied") is { IsTruthy: true };
        var message = result.Get("message") is { } text ? PyConvert.Str(text) : string.Empty;
        await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
            ActivityEventTypes.SystemReconciliationRepair,
            "system",
            applied ? "System repair action completed" : "System repair action skipped",
            $"{action}: {message}")).ConfigureAwait(false);
        return ApiRoutes.Ok(result);
    }
}
