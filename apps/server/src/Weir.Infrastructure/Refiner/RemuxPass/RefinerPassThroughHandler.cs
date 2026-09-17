using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// Worker handler for <c>refiner.file.pass_through.v1</c> (port of <c>make_refiner_file_pass_through_handler</c>): hand
/// the unmodified original back to the output folder once retries are exhausted, then tell a waiting manager it is ready.
/// </summary>
/// <remarks>
/// Runs as its own durable job, and the copy holds no unit of work open (#465): failures are recorded inside a
/// transaction, and a pass-through can be a very large copy, so it only ever queues delivery. The worker reads the
/// library, closes its unit of work, copies, then opens a brief transaction for bookkeeping.
/// </remarks>
public sealed class RefinerPassThroughHandler : IJobHandler
{
    private readonly SqliteDatabase _database;
    private readonly TimeProvider _time;
    private readonly ILogger<RefinerPassThroughHandler> _logger;
    private readonly HandoffCompletionReporter? _reporter;

    public RefinerPassThroughHandler(SqliteDatabase database, TimeProvider time, ILogger<RefinerPassThroughHandler> logger, HandoffCompletionReporter? reporter = null)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _reporter = reporter;
    }

    public string JobKind => IntakeRules.PassThroughJobKind;

    public async Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var payload = FollowUpJobPayload.Parse(context.PayloadJson);
        var relativePath = FollowUpJobPayload.RelativeMediaPath(payload);
        var libraryId = FollowUpJobPayload.LibraryId(payload);
        if (relativePath.Length == 0 || libraryId is null)
        {
            throw new InvalidOperationException("A pass-through job needs a file and a library.");
        }

        // 1. Read what the delivery needs, then close the unit of work before touching any file.
        var delivery = await LockedWrites.RunAsync(
            _database,
            async uow =>
            {
                var library = await RemuxPassHandler.ResolveLibraryAsync(uow, libraryId, null).ConfigureAwait(false);
                if (library is null)
                {
                    throw new InvalidOperationException($"Library {libraryId} no longer exists, so there is nowhere to hand the file back to.");
                }

                return new PassThroughDeliverySettings(library.Id, library.WatchedFolder, library.OutputFolder, library.OutputCollisionPolicy);
            },
            _logger,
            "pass-through claim",
            cancellationToken).ConfigureAwait(false);

        // 2. The copy, with no transaction open — this can take minutes on a large file.
        PassThroughDeliveryResult result;
        try
        {
            result = await PassThroughDelivery.DeliverUnchangedAsync(delivery, relativePath).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or PassThroughIntegrityException or FileNotFoundException or InvalidOperationException)
        {
            _logger.LogWarning(exception, "Refiner pass-through could not deliver {Path}.", relativePath);
            await LockedWrites.RunAsync(
                _database,
                uow => SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
                    ActivityEventTypes.RefinerFilePassThroughFailed,
                    "refiner",
                    $"{MediaPathNames.Name(relativePath, OperatingSystem.IsWindows())} could not be handed back",
                    PyJsonWriter.Dumps(
                        new PyDict()
                            .Set("job_id", context.Id)
                            .Set("relative_media_path", relativePath)
                            .Set("message", PyStrings.Slice(exception.Message, 1200))
                            .Set("trigger", "worker")
                            .Set("result", "failed")
                            .Set("library_id", delivery.LibraryId)
                            .Set("source_kept", true)
                            .Set("next_action",
                                "The original is untouched in the watched folder. Check that the output folder exists and is writable."),
                        PyJsonFormat.Compact))),
                _logger,
                "pass-through failure record",
                cancellationToken).ConfigureAwait(false);

            // Recorded above in plain words; the worker still fails the job but does not say it twice (#488).
            throw new AlreadyRecordedFailureException(exception.Message, exception);
        }

        // 3. Brief bookkeeping.
        var now = _time.GetUtcNow();
        await LockedWrites.RunAsync(
            _database,
            uow => RecordDeliveryAsync(uow, delivery, relativePath, result, context.Id, now),
            _logger,
            "pass-through delivery record",
            cancellationToken).ConfigureAwait(false);

        // 4. Tell a waiting manager the file is ready. Only when something was actually delivered: after a collision
        // skip the file at that path is not this one, and asking the manager to import it would be wrong. Reporting
        // never raises; the delivery already succeeded.
        var origin = FollowUpJobPayload.Origin(payload);
        if (origin is { IsTruthy: true } && result.Delivered && _reporter is not null)
        {
            var reportResult = new PyDict()
                .Set("ok", true)
                .Set("outcome", "live_output_written")
                .Set("relative_media_path", relativePath)
                .Set("output_file", result.Destination)
                .Set("refiner_output_folder_resolved", RemuxPassPaths.Resolve(delivery.OutputFolder))
                .Set("passed_through_after_failure", true);
            var reportPayload = PyJsonWriter.Dumps(new PyDict().Set("origin", origin), PyJsonFormat.Compact);
            var uow = await UnitOfWork.OpenAsync(_database, cancellationToken).ConfigureAwait(false);
            string status;
            await using (uow.ConfigureAwait(false))
            {
                status = await _reporter.ReportHandoffCompletionAsync(uow, reportPayload, reportResult, cancellationToken).ConfigureAwait(false);
            }

            _logger.LogInformation("Refiner pass-through hand-off report: {Status}", status);
        }
    }

    /// <summary><c>record_delivery</c>: the short bookkeeping transaction after a delivery.</summary>
    private static async Task RecordDeliveryAsync(UnitOfWork uow, PassThroughDeliverySettings settings, string relativePath, PassThroughDeliveryResult result, long jobId, DateTimeOffset now)
    {
        await RemuxPassFileState.RecordOutputCollisionAsync(uow, relativePath, result.Collision, settings.LibraryId).ConfigureAwait(false);
        await RemuxPassFileState.MarkFileStatusAsync(uow, settings.LibraryId, relativePath, RefinerFileStatuses.PassedThrough, result.Sentence, now).ConfigureAwait(false);
        var detail = new PyDict()
            .Set("job_id", jobId)
            .Set("relative_media_path", relativePath)
            .Set("library_id", settings.LibraryId)
            .Set("delivered", result.Delivered)
            .Set("destination", result.Destination)
            .Set("collision_action", result.Collision.Action)
            .Set("source_kept", true)
            .Set("message", result.Sentence)
            .Set("trigger", "worker")
            .Set("result", result.Delivered ? "success" : "skipped");
        await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(
            ActivityEventTypes.RefinerFilePassedThrough,
            "refiner",
            $"{MediaPathNames.Name(relativePath, OperatingSystem.IsWindows())} was handed back unchanged",
            PyStrings.Slice(PyJsonWriter.Dumps(detail, PyJsonFormat.Compact), 10_000))).ConfigureAwait(false);
    }
}
