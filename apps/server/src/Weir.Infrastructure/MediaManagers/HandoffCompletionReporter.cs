using System.Globalization;
using System.Net.Http.Headers;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Activity;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.MediaManagers;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.MediaManagers;

/// <summary>Where, and as whom, to report on one hand-off (<c>HandoffReportTarget</c>).</summary>
public sealed record HandoffReportTarget(ManagerConnection Connection, string Url, IReadOnlyDictionary<string, string> Headers);

/// <summary>
/// Reports a finished hand-off to the manager that asked for it (port of <c>completion_callback</c>). The processing
/// port calls <see cref="ReportHandoffCompletionAsync"/> when a pass ends; the reject policy uses the parts.
/// </summary>
public sealed class HandoffCompletionReporter
{
    private readonly MediaManagerConnectionService _connections;
    private readonly HandoffLedgerStore _ledger;
    private readonly IManagerHttpHandlerFactory _handlers;
    private readonly ILogger _logger;

    public HandoffCompletionReporter(
        MediaManagerConnectionService connections,
        HandoffLedgerStore ledger,
        IManagerHttpHandlerFactory handlers,
        ILogger<HandoffCompletionReporter>? logger = null)
    {
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
        _handlers = handlers ?? throw new ArgumentNullException(nameof(handlers));
        _logger = (ILogger?)logger ?? NullLogger.Instance;
    }

    /// <summary><c>resolve_handoff_target</c>: the manager to report to, or a sentence saying why there is none.</summary>
    public async Task<(HandoffReportTarget? Target, string? Reason)> ResolveHandoffTargetAsync(UnitOfWork uow, HandoffOrigin origin)
    {
        ArgumentNullException.ThrowIfNull(origin);
        if (string.IsNullOrEmpty(origin.CallbackPath))
        {
            return (null, "the hand-off named no callback path");
        }

        var connection = await MediaManagerConnectionStore.FirstEnabledForKindAsync(uow, origin.SourceKey).ConfigureAwait(false);
        if (connection is null)
        {
            return (null, $"no enabled {origin.SourceKey} connection is configured to report back to");
        }

        var target = _connections.ResolveCallbackTarget(connection);
        if (target is null)
        {
            return (null, $"the {connection.Name} connection has no address saved");
        }

        var headers = new Dictionary<string, string>(StringComparer.Ordinal) { ["Content-Type"] = "application/json" };
        if (!string.IsNullOrEmpty(target.ApiKey))
        {
            headers["X-Api-Key"] = target.ApiKey;
        }

        return (
            new HandoffReportTarget(
                new ManagerConnection(connection.Kind, connection.Name, target.BaseUrl, target.ApiKey ?? string.Empty, connection.Id),
                $"{target.BaseUrl}/{origin.CallbackPath.TrimStart('/')}",
                headers),
            null);
    }

    /// <summary><c>post_handoff_report</c>: one POST, no redirects, never throws.</summary>
    public async Task<HandoffReportDelivery> PostHandoffReportAsync(HandoffReportTarget target, PyDict body, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(target);
        ArgumentNullException.ThrowIfNull(body);
        var name = target.Connection.Name;
        int status;
        try
        {
            using var client = new HttpClient(_handlers.Handler(followRedirects: false), disposeHandler: false) { Timeout = CompletionReports.Timeout };
            using var request = new HttpRequestMessage(HttpMethod.Post, target.Url)
            {
                // httpx 0.28's json= encoding: compact, UTF-8, no ASCII escaping.
                Content = new ByteArrayContent(PyJsonWriter.DumpsUtf8(body, PyJsonFormat.Response)),
            };
            request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
            foreach (var (header, value) in target.Headers)
            {
                if (!string.Equals(header, "Content-Type", StringComparison.OrdinalIgnoreCase))
                {
                    request.Headers.TryAddWithoutValidation(header, value);
                }
            }

            using var response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
            status = (int)response.StatusCode;
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException or TaskCanceledException or UriFormatException or InvalidOperationException)
        {
            _logger.LogWarning("Hand-off report to {Url} failed: {Error}", target.Url, exception.Message);
            return new HandoffReportDelivery(false, $"failed: could not reach {name}");
        }

        if (status is >= 200 and < 300)
        {
            return new HandoffReportDelivery(true, $"reported {PyConvert.Str(body["status"])} to {name}");
        }

        _logger.LogWarning("Hand-off report to {Url} returned HTTP {Status}", target.Url, status);
        return new HandoffReportDelivery(false, $"failed: {name} answered HTTP {status.ToString(CultureInfo.InvariantCulture)}");
    }

    /// <summary><c>record_handoff_report</c>: the report in Activity, in plain words, accepted or not.</summary>
    public static Task RecordHandoffReportAsync(UnitOfWork uow, HandoffReportTarget target, PyDict body, HandoffReportDelivery delivery, string? relativePath)
    {
        ArgumentNullException.ThrowIfNull(target);
        ArgumentNullException.ThrowIfNull(body);
        ArgumentNullException.ThrowIfNull(delivery);
        var name = target.Connection.Name;
        var fileName = !string.IsNullOrEmpty(relativePath)
            ? MediaPathNames.Name(relativePath, OperatingSystem.IsWindows())
            : body.Get("releaseName") is { IsTruthy: true } release ? PyConvert.Str(release) : "a handed-over file";
        string title;
        if (!delivery.Accepted)
        {
            title = $"Weir could not tell {name} about {fileName}";
        }
        else if (body.Get("disposition") is PyStr { Value: "rejected" })
        {
            title = $"Told {name} that {fileName} is a bad release and was removed";
        }
        else if (body.Get("status") is PyStr { Value: "completed" })
        {
            title = $"Told {name} that {fileName} is ready to import";
        }
        else
        {
            title = $"Told {name} that Weir could not process {fileName}";
        }

        var detail = new PyDict()
            .Set("relative_media_path", relativePath)
            .Set("manager", name)
            .Set("accepted", delivery.Accepted)
            .Set("delivery", delivery.Status)
            .Set("report", body)
            .Set("trigger", "worker")
            .Set("result", delivery.Accepted ? "success" : "failed");
        if (!delivery.Accepted)
        {
            detail.Set(
                "next_action",
                $"Check that {name} is running and that its address and API key are right on the Media managers settings page.");
        }

        return SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
            ActivityEventTypes.ProcessingHandoffReported,
            "processing",
            title,
            PyStrings.Slice(PyJsonWriter.Dumps(detail, PyJsonFormat.Compact), 10_000)));
    }

    /// <summary>
    /// <c>report_handoff_completion</c>: post the outcome back to the originating manager and record that it did. Returns a
    /// short status for logging and never throws: a manager being unreachable must not fail a pass that succeeded on disk.
    /// Commits <paramref name="uow"/> (or rolls it back when recording fails), as the Python session does.
    /// </summary>
    public async Task<string> ReportHandoffCompletionAsync(UnitOfWork uow, string? payloadJson, PyDict result, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(result);
        PyJson? payload = null;
        if (!string.IsNullOrEmpty(payloadJson))
        {
            try
            {
                payload = PyJsonParser.Parse(payloadJson);
            }
            catch (PyJsonDecodeException)
            {
                return "skipped: job payload is not readable";
            }
        }

        var origin = HandoffOrigin.FromPayload(payload);
        if (origin is null)
        {
            return "skipped: not a hand-off";
        }

        if (string.IsNullOrEmpty(origin.CallbackPath))
        {
            return "skipped: the hand-off named no callback path";
        }

        var succeeded = CompletionReports.IsSucceeded(result);
        if (!succeeded && result.Get("retry_scheduled") is PyBool { Value: true })
        {
            return "skipped: the failure will be retried, so it is not final yet";
        }

        if (!succeeded && result.Get("pass_through_queued") is PyBool { Value: true })
        {
            return "skipped: the original is being handed back, which will be reported when it is delivered";
        }

        if (!succeeded && result.Get("reject_queued") is PyBool { Value: true })
        {
            return "skipped: the release is being rejected, which reports on its own";
        }

        var (target, reason) = await ResolveHandoffTargetAsync(uow, origin).ConfigureAwait(false);
        if (target is null)
        {
            await RecordOutcomeAsync(uow, origin, CompletionReports.BuildCompletionBody(origin, result), null).ConfigureAwait(false);
            return $"skipped: {reason}";
        }

        var outputPath = succeeded ? await ManagerOutputPathAsync(target.Connection, origin, result, cancellationToken).ConfigureAwait(false) : null;
        var body = CompletionReports.BuildCompletionBody(origin, result, outputPath);
        var delivery = await PostHandoffReportAsync(target, body, cancellationToken).ConfigureAwait(false);
        var relative = result.Get("relative_media_path") is PyStr text ? text.Value : null;
        await RecordOutcomeAsync(uow, origin, body, (target, delivery, relative)).ConfigureAwait(false);
        return delivery.Status;
    }

    /// <summary>
    /// <c>translate_output_path</c>: <paramref name="outputFile"/> rebuilt under the manager's output folder, or null when it is
    /// not under ours.
    /// </summary>
    public static string? TranslateOutputPath(string outputFile, string localOutputFolder, string managerOutputFolder)
    {
        string file;
        string folder;
        try
        {
            file = Path.GetFullPath(outputFile);
            folder = Path.GetFullPath(localOutputFolder);
        }
        catch (Exception exception) when (exception is ArgumentException or IOException or NotSupportedException or System.Security.SecurityException)
        {
            return null;
        }

        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var fileParts = file.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar).Where(p => p.Length > 0).ToList();
        var folderParts = folder.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar).Where(p => p.Length > 0).ToList();
        if (fileParts.Count <= folderParts.Count || !folderParts.Select((part, i) => string.Equals(part, fileParts[i], comparison)).All(same => same))
        {
            return null;
        }

        return CompletionReports.ManagerPathJoin(managerOutputFolder, fileParts.Skip(folderParts.Count));
    }

    /// <summary><c>_manager_output_path</c>: the output as the manager will see it, or null to fall back to the local path.</summary>
    private async Task<string?> ManagerOutputPathAsync(ManagerConnection connection, HandoffOrigin origin, PyDict result, CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(origin.LibraryId) || result.Get("output_file") is not PyStr outputFile || result.Get("processing_output_folder_resolved") is not PyStr localFolder)
        {
            return null;
        }

        if (_connections.Ports.PortForKind(connection.Kind) is not { } port)
        {
            return null;
        }

        ManagerDescription description;
        try
        {
            description = await port.DescribeAsync(connection, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            _logger.LogWarning(exception, "Could not read {Label}'s libraries to place the output path.", connection.Label);
            return null;
        }

        foreach (var library in description.Libraries)
        {
            if (library.Key == origin.LibraryId && library.ProcessesBeforeImport && !string.IsNullOrEmpty(library.OutputPath))
            {
                return TranslateOutputPath(outputFile.Value, localFolder.Value, library.OutputPath);
            }
        }

        return null;
    }

    /// <summary><c>_record_outcome</c>: keep the ledger and Activity in step with a final outcome, then commit. Never throws.</summary>
    private async Task RecordOutcomeAsync(UnitOfWork uow, HandoffOrigin origin, PyDict body, (HandoffReportTarget Target, HandoffReportDelivery Delivery, string? Relative)? report)
    {
        try
        {
            string state;
            if (body.Get("status") is PyStr { Value: "completed" })
            {
                state = body.Get("message") is PyStr { Value: CompletionReports.PassThroughAfterFailureMessage }
                    ? HandoffLedgerRules.PassedThrough
                    : HandoffLedgerRules.Completed;
            }
            else
            {
                state = HandoffLedgerRules.Failed;
            }

            await _ledger.RecordOutcomeAsync(
                uow,
                origin.SourceKey,
                origin.HandoffId,
                state,
                body.Get("outputPath") is PyStr output ? output.Value : null,
                body.Get("message") is PyStr message ? message.Value : null).ConfigureAwait(false);
            if (report is { } sent)
            {
                await RecordHandoffReportAsync(uow, sent.Target, body, sent.Delivery, sent.Relative).ConfigureAwait(false);
            }

            await uow.CommitAsync().ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is Microsoft.Data.Sqlite.SqliteException or InvalidOperationException or IOException)
        {
            await uow.RollbackAsync().ConfigureAwait(false);
            _logger.LogWarning(exception, "Could not record the hand-off outcome.");
        }
    }
}
