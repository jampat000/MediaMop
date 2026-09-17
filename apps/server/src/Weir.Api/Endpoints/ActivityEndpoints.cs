using System.Globalization;
using System.Numerics;
using System.Text;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Logging;
using Weir.Api.Http;
using Weir.Core.Activity;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Time;
using Weir.Core.Validation;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Settings;

namespace Weir.Api.Endpoints;

/// <summary>
/// The Activity feed: recent history with filters, export, one file's history and its removal, and the
/// live freshness stream (port of <c>weir.platform.activity.router</c>).
/// </summary>
public static class ActivityEndpoints
{
    /// <summary><c>_STREAM_RETRY_MS</c>.</summary>
    public const int StreamRetryMilliseconds = 5000;

    /// <summary><c>_STREAM_KEEPALIVE_EVERY_POLLS</c>.</summary>
    public const int StreamKeepaliveEveryPolls = 8;

    /// <summary><c>_STREAM_POLL_SECONDS</c>.</summary>
    public static readonly TimeSpan StreamPoll = TimeSpan.FromSeconds(2);

    private const string FormatPattern = "^(csv|json)$";

    public static IEndpointRouteBuilder MapActivityEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("GET", "/activity/recent", GetRecentAsync);
        endpoints.MapV1("GET", "/activity/stream", GetStreamAsync);
        endpoints.MapV1("GET", "/activity/export", GetExportAsync);
        endpoints.MapV1("GET", "/activity/file-history", GetFileHistoryAsync);
        endpoints.MapV1("POST", "/activity/file-history/remove", PostFileHistoryRemoveAsync);
        return endpoints;
    }

    private static async Task<ApiResult> GetRecentAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var limit = QueryInt(request, "limit", issues, ge: 1, le: 100) ?? ActivityHistory.RecentDefaultLimit;
        var module = QueryStr(request, "module", issues, 1, 32);
        var eventType = QueryStr(request, "event_type", issues, 1, 64);
        var search = QueryStr(request, "search", issues, 1, 200);
        var dateFrom = request.Query("date_from");
        var dateTo = request.Query("date_to");
        var beforeId = QueryInt(request, "before_id", issues, ge: 1);
        var trigger = QueryStr(request, "trigger", issues, 1, 32);
        var result = QueryStr(request, "result", issues, 1, 16);
        var libraryId = QueryInt(request, "library_id", issues, ge: 1);
        var file = QueryStr(request, "file", issues, 1, 2000);
        issues.ThrowIfAny();

        var filter = new ActivityFilter(module, eventType, search, ParseWhen(dateFrom, "date_from"), ParseWhen(dateTo, "date_to"), trigger, result, libraryId, file);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var rows = await ActivityHistoryStore.ListRecentAsync(uow, filter, limit, beforeId).ConfigureAwait(false);
        var total = await ActivityHistoryStore.CountAsync(uow, filter).ConfigureAwait(false);
        var systemEvents = await ActivityHistoryStore.CountSystemAsync(uow, filter).ConfigureAwait(false);
        var settings = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var oldest = await ActivityHistoryStore.OldestCreatedAtAsync(uow).ConfigureAwait(false);
        return ApiRoutes.Ok(ActivityHistory.RecentOut(rows, total, systemEvents, settings.ActivityRetentionDays, oldest));
    }

    private static async Task<ApiResult> GetExportAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var format = "csv";
        if (request.Query("format") is { } rawFormat)
        {
            if (rawFormat is "csv" or "json")
            {
                format = rawFormat;
            }
            else
            {
                issues.Add(new ValidationIssue(
                    "string_pattern_mismatch",
                    ["query", "format"],
                    $"String should match pattern '{FormatPattern}'",
                    new PyStr(rawFormat),
                    new PyDict().Set("pattern", FormatPattern)));
            }
        }

        var module = QueryStr(request, "module", issues, 1, 32);
        var eventType = QueryStr(request, "event_type", issues, 1, 64);
        var search = QueryStr(request, "search", issues, 1, 200);
        var dateFrom = request.Query("date_from");
        var dateTo = request.Query("date_to");
        var trigger = QueryStr(request, "trigger", issues, 1, 32);
        var result = QueryStr(request, "result", issues, 1, 16);
        var libraryId = QueryInt(request, "library_id", issues, ge: 1);
        var file = QueryStr(request, "file", issues, 1, 2000);
        issues.ThrowIfAny();

        var filter = new ActivityFilter(module, eventType, search, ParseWhen(dateFrom, "date_from"), ParseWhen(dateTo, "date_to"), trigger, result, libraryId, file);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var rows = await ActivityHistoryStore.ListForExportAsync(uow, filter).ConfigureAwait(false);
        var localNow = request.Time.GetLocalNow();
        var json = format == "json";
        var text = json ? ActivityHistory.ExportJson(rows) : ActivityHistory.ExportCsv(rows);
        var fileName = ActivityHistory.ExportFileName(localNow, json ? "json" : "csv");
        return new CustomApiResult(async context =>
        {
            context.Response.Headers["X-Weir-Export-Limit"] = ActivityHistory.ExportMaxRows.ToString(CultureInfo.InvariantCulture);
            context.Response.Headers["X-Weir-Export-Rows"] = rows.Count.ToString(CultureInfo.InvariantCulture);
            context.Response.Headers.ContentDisposition = $"attachment; filename=\"{fileName}\"";
            await PyResponses.WritePlainTextAsync(context, StatusCodes.Status200OK, text, json ? "application/json" : "text/csv; charset=utf-8").ConfigureAwait(false);
        });
    }

    private static async Task<ApiResult> GetFileHistoryAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        string? relativePath = null;
        if (request.Query("relative_path") is not null)
        {
            relativePath = QueryStr(request, "relative_path", issues, 1, 2000);
        }
        else
        {
            issues.Add(PydanticRules.Missing(["query", "relative_path"], PyNull.Instance));
        }

        var libraryId = QueryInt(request, "library_id", issues, ge: 1);
        issues.ThrowIfAny();

        var path = PyStrings.Strip(relativePath!);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var counts = await ActivityHistoryStore.CountFileHistoryAsync(uow, libraryId, path).ConfigureAwait(false);
        return ApiRoutes.Ok(ActivityHistory.FileHistoryCountOut(counts));
    }

    private static async Task<ApiResult> PostFileHistoryRemoveAsync(ApiRequest request)
    {
        var body = await request.ReadBodyAsync().ConfigureAwait(false);
        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        var issues = new ValidationIssues();
        var model = new BodyModel(body, issues);
        var libraryId = model.OptionalInt("library_id", ge: 1);
        var relativePath = model.Str("relative_path", minLength: 1, maxLength: 2000);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        model.Finish(ExtraFields.Ignore);
        issues.ThrowIfAny();

        request.RequireConfirmationToken(csrfToken);
        var path = PyStrings.Strip(relativePath);
        var uow = await request.DbAsync().ConfigureAwait(false);
        var deleted = await ActivityHistoryStore.DeleteFileHistoryAsync(uow, libraryId, path).ConfigureAwait(false);
        await request.CommitAsync().ConfigureAwait(false);
        return ApiRoutes.Ok(ActivityHistory.FileHistoryRemoveOut(deleted));
    }

    /// <summary>
    /// <c>get_activity_stream</c>: authenticate once with a short-lived connection, then stream
    /// <c>activity.latest</c> frames and keepalives without holding the database.
    /// </summary>
    private static async Task<ApiResult> GetStreamAsync(ApiRequest request)
    {
        await request.RequireUserAsync().ConfigureAwait(false);
        await request.ReleaseDbAsync().ConfigureAwait(false);
        var database = request.Database;
        var notifier = ActivityNotifications.For(database);
        var time = request.Time;
        var logger = request.LoggerFactory.CreateLogger("weir.platform.activity.router");
        return new CustomApiResult(async context =>
        {
            context.Response.StatusCode = StatusCodes.Status200OK;
            context.Response.ContentType = "text/event-stream; charset=utf-8";
            context.Response.Headers.CacheControl = "no-store, no-cache";
            context.Response.Headers.Connection = "keep-alive";
            context.Response.Headers["X-Accel-Buffering"] = "no";
            try
            {
                await foreach (var chunk in LatestFramesAsync(
                    ct => ActivityHistoryStore.LatestIdAsync(database, ct),
                    notifier,
                    time,
                    StreamPoll,
                    StreamKeepaliveEveryPolls,
                    logger,
                    context.RequestAborted).ConfigureAwait(false))
                {
                    await context.Response.Body.WriteAsync(Encoding.UTF8.GetBytes(chunk), context.RequestAborted).ConfigureAwait(false);
                    await context.Response.Body.FlushAsync(context.RequestAborted).ConfigureAwait(false);
                }
            }
            catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested)
            {
                // The client went away.
            }
        });
    }

    /// <summary>
    /// <c>iter_activity_latest_sse</c>: the retry hint, then a frame whenever the latest id or the notifier's
    /// revision changes, and a keepalive comment after <paramref name="keepaliveEveryPolls"/> quiet polls.
    /// </summary>
    public static async IAsyncEnumerable<string> LatestFramesAsync(
        Func<CancellationToken, Task<long?>> readLatestId,
        ActivityLatestNotifier notifier,
        TimeProvider time,
        TimeSpan poll,
        int keepaliveEveryPolls,
        ILogger logger,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(readLatestId);
        ArgumentNullException.ThrowIfNull(notifier);
        ArgumentNullException.ThrowIfNull(time);
        ArgumentNullException.ThrowIfNull(logger);
        long? lastSentId = null;
        var lastSeenVersion = notifier.Snapshot().Version;
        var pollsSinceKeepalive = 0;
        yield return string.Create(CultureInfo.InvariantCulture, $"retry: {StreamRetryMilliseconds}\n\n");
        while (!cancellationToken.IsCancellationRequested)
        {
            long? latestId;
            try
            {
                latestId = await readLatestId(cancellationToken).ConfigureAwait(false);
            }
            catch (Exception exception) when (exception is not OperationCanceledException)
            {
                logger.LogWarning("SSE activity stream: read_latest_id failed, retrying after back-off");
                await Task.Delay(poll, time, cancellationToken).ConfigureAwait(false);
                continue;
            }

            if (latestId is { } id && id != lastSentId)
            {
                lastSentId = id;
                lastSeenVersion = Math.Max(lastSeenVersion, notifier.Snapshot().Version);
                yield return ActivityHistory.LatestEventFrame(id, lastSeenVersion);
                pollsSinceKeepalive = 0;
                continue;
            }

            if (await notifier.WaitForChangeAsync(lastSeenVersion, poll, time, cancellationToken).ConfigureAwait(false) is { } changed)
            {
                lastSeenVersion = changed.Version;
                if (changed.LatestId is { } changedId)
                {
                    lastSentId = changedId;
                    yield return ActivityHistory.LatestEventFrame(changedId, lastSeenVersion);
                    pollsSinceKeepalive = 0;
                    continue;
                }
            }

            pollsSinceKeepalive++;
            if (pollsSinceKeepalive >= keepaliveEveryPolls)
            {
                yield return ": keepalive\n\n";
                pollsSinceKeepalive = 0;
            }
        }
    }

    /// <summary><c>datetime.fromisoformat</c> of a date query, or 400 <c>Invalid {name}.</c> (an empty value is no filter).</summary>
    private static PyDateTime? ParseWhen(string? raw, string name)
    {
        if (string.IsNullOrEmpty(raw))
        {
            return null;
        }

        return PyDateTime.TryFromIsoFormat(raw, out var value)
            ? value
            : throw new ApiException(StatusCodes.Status400BadRequest, $"Invalid {name}.");
    }

    private static string? QueryStr(ApiRequest request, string name, ValidationIssues issues, int minLength, int maxLength)
    {
        var raw = request.Query(name);
        if (raw is null)
        {
            return null;
        }

        return PydanticRules.TryStr(new PyStr(raw), ["query", name], minLength, maxLength, issues, out var value) ? value : null;
    }

    private static long? QueryInt(ApiRequest request, string name, ValidationIssues issues, long? ge = null, long? le = null)
    {
        var raw = request.Query(name);
        if (raw is null || !PydanticRules.TryInt(new PyStr(raw), ["query", name], ge, le, issues, out var value))
        {
            return null;
        }

        return value > long.MaxValue ? long.MaxValue : (long)BigInteger.Max(value, long.MinValue);
    }
}
