using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// Worker handler for <c>refiner.file.reject.v1</c> (port of <c>make_refiner_file_reject_handler</c>): tell the media
/// manager a release Weir could not process is bad, so it can find a different one (#465, #471).
/// </summary>
/// <remarks>
/// <para>
/// <b>Report first, remove second.</b> Nothing is removed until the manager has accepted the report (a 2xx answer); "could
/// not reach it" and "it refused" are treated the same: not accepted.
/// </para>
/// <para>
/// <b>Anything short of certainty falls back to pass-through</b> — never to deleting a file nobody was told about, and
/// never to silently doing nothing. The fallback is recorded in Activity with the reason.
/// </para>
/// <para>
/// Fix #532: whichever way the attempt ends, a Files row is upserted (not merely updated) so a rejection that no scan
/// had seen still appears on the Files screen.
/// </para>
/// </remarks>
public sealed class RefinerRejectHandler : IJobHandler
{
    private static readonly StringComparison PathComparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;

    private readonly SqliteDatabase _database;
    private readonly IMediaManagerPorts _ports;
    private readonly MediaManagerConnectionService _connections;
    private readonly HandoffCompletionReporter _reporter;
    private readonly HandoffLedgerStore _ledger;
    private readonly RefinerJobStore _jobs;
    private readonly RejectPacing _pacing;
    private readonly TimeProvider _time;
    private readonly ILogger<RefinerRejectHandler> _logger;

    public RefinerRejectHandler(
        SqliteDatabase database,
        IMediaManagerPorts ports,
        MediaManagerConnectionService connections,
        HandoffCompletionReporter reporter,
        HandoffLedgerStore ledger,
        RefinerJobStore jobs,
        RejectPacing pacing,
        TimeProvider time,
        ILogger<RefinerRejectHandler> logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _ports = ports ?? throw new ArgumentNullException(nameof(ports));
        _connections = connections ?? throw new ArgumentNullException(nameof(connections));
        _reporter = reporter ?? throw new ArgumentNullException(nameof(reporter));
        _ledger = ledger ?? throw new ArgumentNullException(nameof(ledger));
        _jobs = jobs ?? throw new ArgumentNullException(nameof(jobs));
        _pacing = pacing ?? throw new ArgumentNullException(nameof(pacing));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public string JobKind => IntakeRules.RejectJobKind;

    private sealed record ReportEnvelope(HandoffReportTarget Target, PyDict Body, HandoffReportDelivery Delivery);

    private sealed record RejectAttempt(bool Done, string Reason, string? Manager = null, PyDict? Detail = null, ReportEnvelope? Report = null)
    {
        public PyDict DetailOrEmpty => Detail ?? new PyDict();
    }

    public async Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var payload = FollowUpJobPayload.Parse(context.PayloadJson);
        var relativePath = FollowUpJobPayload.RelativeMediaPath(payload);
        var libraryId = FollowUpJobPayload.LibraryId(payload);
        if (relativePath.Length == 0 || libraryId is null)
        {
            throw new InvalidOperationException("A reject job needs a file and a library.");
        }

        var originRaw = FollowUpJobPayload.Origin(payload);
        var reason = payload.Get("reason") is PyStr reasonValue && reasonValue.Value.Length > 0
            ? reasonValue.Value
            : "Weir could not process this file.";
        var failureClass = payload.Get("failure_class") is PyStr failureClassValue ? failureClassValue.Value : null;
        var origin = originRaw is not null ? HandoffOrigin.FromPayload(new PyDict().Set("origin", originRaw)) : null;

        // 1. Everything the attempt needs, read with the unit of work closed before any network call.
        string watchedRoot = string.Empty;
        HandoffReportTarget? target = null;
        string? targetRefusalReason = null;
        var queueConnections = new List<ManagerConnection>();
        await LockedWrites.RunAsync(
            _database,
            async uow =>
            {
                var library = await RemuxPassHandler.ResolveLibraryAsync(uow, libraryId, null).ConfigureAwait(false);
                if (library is null)
                {
                    throw new InvalidOperationException($"Library {libraryId} no longer exists.");
                }

                watchedRoot = RemuxPassPaths.Resolve(library.WatchedFolder);
                if (origin is not null && _ports.PortForKind(origin.SourceKey) is { } originPort && !originPort.Capabilities().RemovesQueueItems)
                {
                    (target, targetRefusalReason) = await _reporter.ResolveHandoffTargetAsync(uow, origin).ConfigureAwait(false);
                }

                var connectionIds = await LibraryStore.ManagerConnectionIdsAsync(uow, library.Id).ConfigureAwait(false);
                var linked = await _connections.ConnectionsByIdAsync(uow, connectionIds).ConfigureAwait(false);
                queueConnections = [.. linked.Where(connection => _ports.PortForKind(connection.Kind)?.Capabilities().RemovesQueueItems == true)];
            },
            _logger,
            "reject claim",
            cancellationToken).ConfigureAwait(false);

        var source = RemuxPassPaths.Resolve(Path.Combine(watchedRoot, relativePath));

        // 2. The attempt, paced, with no unit of work open.
        await _pacing.WaitAsync(cancellationToken).ConfigureAwait(false);
        RejectAttempt attempt;
        if (origin is not null)
        {
            attempt = target is not null
                ? await RejectThroughHandoffAsync(target, origin, source, watchedRoot, reason, failureClass, cancellationToken).ConfigureAwait(false)
                : targetRefusalReason is not null
                    ? new RejectAttempt(false, $"Weir could not report to the manager: {targetRefusalReason}.")
                    : queueConnections.Count > 0
                        ? await RejectThroughQueueAsync(queueConnections, source, cancellationToken).ConfigureAwait(false)
                        : new RejectAttempt(false, "No linked media manager can take a rejection for this file, so Weir handed the original back instead.");
        }
        else if (queueConnections.Count > 0)
        {
            attempt = await RejectThroughQueueAsync(queueConnections, source, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            attempt = new RejectAttempt(false, "No linked media manager can take a rejection for this file, so Weir handed the original back instead.");
        }

        // 3. Bookkeeping, and the fallback, in one short transaction.
        var now = _time.GetUtcNow();
        await LockedWrites.RunAsync(
            _database,
            async uow =>
            {
                if (attempt.Report is { } report)
                {
                    await HandoffCompletionReporter.RecordHandoffReportAsync(uow, report.Target, report.Body, report.Delivery, relativePath).ConfigureAwait(false);
                }

                var detail = new PyDict()
                    .Set("job_id", context.Id)
                    .Set("relative_media_path", relativePath)
                    .Set("library_id", libraryId)
                    .Set("manager", attempt.Manager)
                    .Set("message", attempt.Reason)
                    .Set("trigger", "worker")
                    .Set("result", attempt.Done ? "success" : "warning");
                foreach (var (key, value) in attempt.DetailOrEmpty.Items)
                {
                    detail.Set(key, value);
                }

                string eventType;
                string title;
                if (attempt.Done)
                {
                    // Fix #532: always upsert, even when no scan has recorded this file yet. The reason keeps why
                    // the release was rejected (from the job payload — e.g. "no retainable audio") alongside what
                    // happened to the download, rather than the acceptance sentence alone replacing it.
                    var rejectedReason = PyStrings.Slice(PyStrings.Strip($"{reason} {attempt.Reason}"), 10_000);
                    await RemuxPassFileState.UpsertRejectedAsync(uow, libraryId.Value, relativePath, rejectedReason, failureClass).ConfigureAwait(false);
                    if (origin is not null)
                    {
                        await _ledger.RecordOutcomeAsync(uow, origin.SourceKey, origin.HandoffId, HandoffLedgerRules.Rejected, null, attempt.Reason).ConfigureAwait(false);
                    }

                    eventType = ActivityEventTypes.RefinerFileRejected;
                    title = $"{MediaPathNames.Name(relativePath, OperatingSystem.IsWindows())} was rejected so a different release can be found";
                }
                else
                {
                    var liveLibrary = await RemuxPassHandler.ResolveLibraryAsync(uow, libraryId, null).ConfigureAwait(false);
                    if (liveLibrary is not null)
                    {
                        EnqueuePassThroughFallback(uow, liveLibrary, relativePath, originRaw);
                    }

                    await RemuxPassFileState.MarkFileStatusAsync(
                        uow, libraryId.Value, relativePath, RefinerFileStatuses.ProcessingFailed,
                        PyStrings.Slice($"{reason} {attempt.Reason} Weir is handing the original back unchanged instead.", 10_000),
                        now).ConfigureAwait(false);
                    eventType = ActivityEventTypes.RefinerFileRejectFellBack;
                    title = $"{MediaPathNames.Name(relativePath, OperatingSystem.IsWindows())} could not be rejected, so it is being handed back";
                    detail.Set("next_action", "Weir queued the original to be handed back unchanged.");
                }

                await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
                    eventType, "refiner", title, PyStrings.Slice(PyJsonWriter.Dumps(detail, PyJsonFormat.Compact), 10_000))).ConfigureAwait(false);
            },
            _logger,
            "reject bookkeeping",
            cancellationToken).ConfigureAwait(false);
        _logger.LogInformation("Reject for {Path}: {Reason}", relativePath, attempt.Reason);
    }

    /// <summary><c>_reject_through_handoff</c>: a manager that hands files over gets a failed report with disposition: rejected.</summary>
    private async Task<RejectAttempt> RejectThroughHandoffAsync(
        HandoffReportTarget target, HandoffOrigin origin, string source, string watchedRoot, string reason, string? failureClass, CancellationToken cancellationToken)
    {
        var connection = target.Connection;
        var label = connection.Label;
        var port = _ports.PortForKind(connection.Kind);
        if (port is null)
        {
            return new RejectAttempt(false, $"Weir does not know how to ask {label} what it can do.", label);
        }

        var description = await port.DescribeAsync(connection, cancellationToken).ConfigureAwait(false);
        if (description.Status != SignalStatus.Reported)
        {
            return new RejectAttempt(false, description.Detail ?? $"Weir could not ask {label} what it can do.", label);
        }

        if (description.AdvertisedCapabilities is null || !description.AdvertisedCapabilities.Contains(RejectSupportRules.RejectCapability))
        {
            return new RejectAttempt(false, $"{label} does not yet say it can replace a rejected release, so Weir did not delete the download.", label);
        }

        if (!File.Exists(source))
        {
            return new RejectAttempt(false, $"The original is no longer at {source}, so there is nothing to reject.");
        }

        var result = new PyDict().Set("ok", false).Set("outcome", "failed").Set("reason", reason);
        if (!string.IsNullOrEmpty(failureClass))
        {
            result.Set("failure_class", failureClass);
        }

        var body = CompletionReports.BuildCompletionBody(origin, result, rejected: true);
        var delivery = await _reporter.PostHandoffReportAsync(target, body, cancellationToken).ConfigureAwait(false);
        var report = new ReportEnvelope(target, body, delivery);
        if (!delivery.Accepted)
        {
            var status = delivery.Status.StartsWith("failed: ", StringComparison.Ordinal) ? delivery.Status["failed: ".Length..] : delivery.Status;
            return new RejectAttempt(false, $"{label} did not accept the rejection ({status}), so Weir kept the download.", label, null, report);
        }

        var cleanup = RemuxPassPaths.CleanupRejectedFile(watchedRoot, source, "delete_file");
        var sentence = cleanup.Deleted
            ? $"{label} accepted that this release is bad and can find a different one. {cleanup.Detail}"
            : $"{label} accepted that this release is bad, but Weir could not remove the download: {cleanup.Detail} Remove it by hand; Weir will not process it again.";
        return new RejectAttempt(true, sentence, label, new PyDict().Set("route", "handoff").Set("source_removed", cleanup.Deleted), report);
    }

    /// <summary><c>_reject_through_queue</c>: a manager whose port removes queue items is asked to remove the matching item.</summary>
    private async Task<RejectAttempt> RejectThroughQueueAsync(List<ManagerConnection> connections, string source, CancellationToken cancellationToken)
    {
        var matches = new List<(ManagerConnection Connection, PyDict Row, bool IsFolder, int Index)>();
        var rowsByConnection = new Dictionary<int, List<PyDict>>();
        var wanted = NormalizeStoragePath(source);
        for (var index = 0; index < connections.Count; index++)
        {
            var connection = connections[index];
            var port = _ports.PortForKind(connection.Kind);
            if (port is null)
            {
                continue;
            }

            var signal = await port.QueueRowsAsync(connection, cancellationToken).ConfigureAwait(false);
            if (!signal.IsReported)
            {
                return new RejectAttempt(false, signal.Detail ?? $"Weir could not read {connection.Label}'s queue.", connection.Label);
            }

            var rows = signal.Rows.Select(row => row.Payload).ToList();
            rowsByConnection[index] = rows;
            foreach (var row in rows)
            {
                var outputPath = PyValues.FirstText(row, "outputPath", "output_path");
                if (outputPath is null)
                {
                    continue;
                }

                var folder = NormalizeStoragePath(outputPath).TrimEnd('/');
                if (folder == wanted)
                {
                    matches.Add((connection, row, false, index));
                }
                else if (folder.Length > 0 && wanted.StartsWith(folder + "/", StringComparison.Ordinal))
                {
                    matches.Add((connection, row, true, index));
                }
            }
        }

        if (matches.Count == 0)
        {
            return new RejectAttempt(false, "No download in the linked media manager's queue points at this file, so Weir could not reject it safely.");
        }

        if (matches.Count > 1)
        {
            return new RejectAttempt(false, "More than one download in the queue points at this file, so Weir could not tell which one to reject.");
        }

        var (matchedConnection, matchedRow, isFolder, matchedIndex) = matches[0];
        var label = matchedConnection.Label;
        var downloadId = PyValues.FirstText(matchedRow, "downloadId");
        if (downloadId is not null)
        {
            var siblings = rowsByConnection.GetValueOrDefault(matchedIndex, []).Count(row => PyValues.FirstText(row, "downloadId") == downloadId);
            if (siblings > 1)
            {
                return new RejectAttempt(
                    false,
                    $"This file is part of a download that {label} tracks as {siblings} items (a season pack or " +
                    "similar). Rejecting it would delete the others too, so Weir handed the original back instead.",
                    label);
            }
        }

        if (isFolder)
        {
            var downloadFolder = PyValues.FirstText(matchedRow, "outputPath", "output_path") ?? string.Empty;
            var only = SingleVideoFileUnder(downloadFolder);
            if (only is null || !string.Equals(only, RemuxPassPaths.Resolve(source), PathComparison))
            {
                return new RejectAttempt(
                    false,
                    $"The download holds more than this one video file. Rejecting it in {label} would delete the " +
                    "others too, so Weir handed the original back instead.",
                    label);
            }
        }

        var removePort = _ports.PortForKind(matchedConnection.Kind);
        if (removePort is null)
        {
            return new RejectAttempt(false, $"Weir does not know how to ask {label} to remove a download.", label);
        }

        try
        {
            await removePort.RemoveQueueItemAsync(matchedConnection, matchedRow, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is MediaManagerHttpException or IOException)
        {
            return new RejectAttempt(
                false, $"{label} did not accept the rejection, so nothing was removed.", label,
                new PyDict().Set("technical_detail", PyStrings.Slice(exception.Message, 500)));
        }

        return new RejectAttempt(
            true,
            $"{label} removed the download and blocklisted the release, so it will not be grabbed again and {label} can search for a different one.",
            label,
            new PyDict().Set("route", "queue").Set("queue_item", matchedRow.Get("id") ?? PyNull.Instance).Set("download_id", downloadId));
    }

    /// <summary><c>enqueue_pass_through</c>, called unconditionally on any reject failure — the reject route never
    /// re-checks the library's failure policy: anything short of certainty always falls back to pass-through.</summary>
    private void EnqueuePassThroughFallback(UnitOfWork uow, RefinerLibraryRecord library, string relativePath, PyDict? origin)
    {
        var body = new PyDict().Set("relative_media_path", relativePath).Set("library_id", library.Id).Set("trigger", "worker");
        if (origin is { IsTruthy: true })
        {
            body.Set("origin", origin);
        }

        _jobs.EnqueueOrGet(
            uow.Connection,
            uow.WriteTransaction(),
            $"{IntakeRules.PassThroughJobKind}:{library.Id}:{relativePath}:{QueueingFailurePolicy.FingerprintTag(library, relativePath)}",
            IntakeRules.PassThroughJobKind,
            PyJsonWriter.Dumps(body, PyJsonFormat.Compact),
            JobQueueRules.DefaultMaxAttempts,
            0,
            (int)Math.Clamp(library.Priority, int.MinValue, int.MaxValue));
    }

    /// <summary><c>normalize_storage_path</c>.</summary>
    private static string NormalizeStoragePath(string path) => path.Replace('\\', '/').Trim().ToLowerInvariant();

    /// <summary><c>_single_video_file_under</c>: the only video file in a download folder, or null.</summary>
    private static string? SingleVideoFileUnder(string folder)
    {
        if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder))
        {
            return null;
        }

        List<string> found;
        try
        {
            found = [.. Directory.EnumerateFiles(folder, "*", SearchOption.AllDirectories)
                .Where(path => RemuxRules.MediaExtensions.Contains(Path.GetExtension(path).ToLowerInvariant()))];
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return null;
        }

        return found.Count == 1 ? RemuxPassPaths.Resolve(found[0]) : null;
    }
}
