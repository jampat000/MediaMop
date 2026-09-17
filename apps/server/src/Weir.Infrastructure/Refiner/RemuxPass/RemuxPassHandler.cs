using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;
using Weir.Core.Activity;
using Weir.Core.Configuration;
using Weir.Core.Jobs;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.MediaManagers;
using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Rules;
using Weir.Core.Time;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.MediaManagers;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner.RemuxPass;

/// <summary>
/// The worker handler for <c>refiner.file.remux_pass.v1</c> (port of <c>file_remux_pass/handlers.py</c>): claim the file, run
/// the pass outside any transaction, keep the Files row and Activity in step with the result, apply the library's failure
/// policy, and report back to the manager that handed the file over.
/// </summary>
/// <remarks>
/// #531 item 2: when a retried or requeued payload has lost its hand-off origin, the origin of the most recent job for the
/// same file is carried forward (<see cref="HandoffOriginCarry"/>), so the final outcome is still reported with its output path.
/// </remarks>
public sealed class RemuxPassHandler : IJobHandler
{
    private readonly SqliteDatabase _database;
    private readonly WeirOptions _options;
    private readonly RemuxPassRunner _runner;
    private readonly IFailurePolicy _failurePolicy;
    private readonly HandoffCompletionReporter? _reporter;
    private readonly TimeProvider _time;
    private readonly ILogger<RemuxPassHandler> _logger;

    public RemuxPassHandler(
        SqliteDatabase database,
        WeirOptions options,
        RemuxPassRunner runner,
        IFailurePolicy failurePolicy,
        TimeProvider time,
        ILogger<RemuxPassHandler> logger,
        HandoffCompletionReporter? reporter = null)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _runner = runner ?? throw new ArgumentNullException(nameof(runner));
        _failurePolicy = failurePolicy ?? throw new ArgumentNullException(nameof(failurePolicy));
        _time = time ?? throw new ArgumentNullException(nameof(time));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _reporter = reporter;
    }

    public string JobKind => RemuxPassOutcomes.JobKind;

    public async Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var raw = PyStrings.Strip(context.PayloadJson ?? string.Empty);
        if (raw.Length == 0)
        {
            await RecordAsync(FailedPayload(context.Id, "missing payload_json")).ConfigureAwait(false);
            return;
        }

        PyJson parsed;
        try
        {
            parsed = PyJsonParser.Parse(raw);
        }
        catch (PyJsonDecodeException exception)
        {
            await RecordAsync(FailedPayload(context.Id, $"invalid json: {exception.Message}")).ConfigureAwait(false);
            return;
        }

        if (parsed is not PyDict data)
        {
            await RecordAsync(FailedPayload(context.Id, "payload must be a JSON object")).ConfigureAwait(false);
            return;
        }

        var provenance = ActivityProvenance.JobProvenance(data);
        if (data.Get("relative_media_path") is not PyStr relValue || PyStrings.Strip(relValue.Value).Length == 0)
        {
            await RecordAsync(Merge(FailedPayload(context.Id, "relative_media_path is required"), provenance)).ConfigureAwait(false);
            return;
        }

        var rel = PyStrings.Strip(relValue.Value);
        if (data.Get("dry_run") is { } dryRun && dryRun is not PyNull)
        {
            var legacy = FailedPayload(
                    context.Id,
                    "This job payload uses legacy Refiner dry_run, which is no longer supported. Re-enqueue without dry_run.")
                .Set("relative_media_path", rel);
            await RecordFailedResultAsync(Merge(legacy, provenance), null, "movie", null).ConfigureAwait(false);
            return;
        }

        var mediaScope = data.Get("media_scope") is PyStr { Value: "movie" or "tv" } scopeValue ? scopeValue.Value : "movie";
        long? libraryId = data.Get("library_id") is PyInt libraryValue ? (long)libraryValue.Value : null;
        var passThrough = data.Get("pass_through_unchanged") is PyBool { Value: true };

        var origin = data.Get("origin") as PyDict;
        var payloadJson = context.PayloadJson;
        if (origin is null)
        {
            origin = await CarriedOriginAsync(context.Id, libraryId, rel, mediaScope).ConfigureAwait(false);
            if (origin is not null)
            {
                var carried = data.Copy().Set("origin", origin);
                payloadJson = PyJsonWriter.Dumps(carried, PyJsonFormat.Compact);
            }
        }

        var claim = await ClaimAsync(context, rel, mediaScope, libraryId, cancellationToken).ConfigureAwait(false);
        if (claim.Failure is { } failure)
        {
            Merge(failure, provenance);
            await RecordFailedResultAsync(failure, libraryId, mediaScope, origin).ConfigureAwait(false);
            await ReportBackAsync(payloadJson, failure).ConfigureAwait(false);
            return;
        }

        var progress = new ActivityProgressReporter(_database, context.Id, provenance, _logger);
        var result = await _runner.RunAsync(
            new RemuxPassRequest
            {
                Runtime = claim.Runtime!,
                RelativeMediaPath = rel,
                LibraryId = claim.Library?.Id ?? libraryId,
                RulesConfig = claim.Rules,
                MinFileAgeSeconds = claim.Operator!.MinFileAgeSeconds,
                MinInputFileSizeMb = Math.Max(claim.Operator.RefinerMinInputFileSizeMb, claim.Library?.MinFileSizeMb ?? 0),
                MinimumFreeDiskSpaceMb = claim.Operator.MinimumFreeDiskSpaceMb,
                MediaScope = mediaScope,
                CurrentJobId = context.Id,
                ProgressReporter = progress.Report,
                PassThroughUnchanged = passThrough,
                Origin = HandoffOrigin.FromPayload(origin is null ? null : new PyDict().Set("origin", origin)),
            },
            cancellationToken).ConfigureAwait(false);
        result.Set("job_id", context.Id);
        result.Set("library_id", claim.Library?.Id ?? libraryId);
        if (result.Get("rejection_kind") is { IsTruthy: true } && claim.Library is { } library)
        {
            var action = string.Equals(PyStrings.Strip(library.RejectedFileAction ?? string.Empty), "delete_file", StringComparison.OrdinalIgnoreCase)
                         // Under reject, the reject job removes the download, and only after the manager accepts.
                         && RefinerFailurePolicies.Normalize(library.FailurePolicy) != RefinerFailurePolicies.Reject
                ? "delete_file"
                : "leave";
            result.Set("rejected_file_action", action);
            if (action == "delete_file")
            {
                result.Set("rejected_cleanup_status", "pending");
                result.Set("rejected_cleanup_detail", "This library is set to delete rejected files. Weir recorded the rejection and will now remove only this file.");
            }
            else
            {
                result.Set("rejected_cleanup_status", "left_in_place");
                result.Set("rejected_cleanup_detail", "Weir left the rejected file in place because this library's cleanup action is Leave in place.");
            }
        }

        Merge(result, provenance);
        await ApplyFileOutcomeStateAsync(result, libraryId, mediaScope, origin).ConfigureAwait(false);
        await RecordAsync(result, progress.ActivityId).ConfigureAwait(false);
        await FinishRejectedInputCleanupAsync(result, libraryId, mediaScope).ConfigureAwait(false);
        await ReportBackAsync(payloadJson, result).ConfigureAwait(false);
    }

    private sealed record Claim(
        PyDict? Failure,
        RefinerOperatorSettingsRecord? Operator = null,
        RefinerLibraryRecord? Library = null,
        RefinerRulesConfig? Rules = null,
        RefinerPathRuntime? Runtime = null);

    /// <summary>
    /// Read what the pass needs and mark the file as being processed, then commit: no ffprobe or ffmpeg work runs while the
    /// worker holds a transaction.
    /// </summary>
    private Task<Claim> ClaimAsync(JobWorkContext context, string rel, string mediaScope, long? libraryId, CancellationToken cancellationToken) =>
        LockedWrites.RunAsync(
            _database,
            async uow =>
            {
                var operatorSettings = await OperatorSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
                var library = await ResolveLibraryAsync(uow, libraryId, mediaScope).ConfigureAwait(false);
                var rules = library is not null ? await RulesConfigForAsync(uow, library).ConfigureAwait(false) : null;
                rules ??= await LoadScopeRulesConfigAsync(uow, mediaScope).ConfigureAwait(false);
                RefinerPathRuntime? runtime;
                string? problem;
                if (library is null)
                {
                    var label = mediaScope == "tv" ? "TV" : "Movies";
                    (runtime, problem) = (null, $"No Refiner library covers {label}. Add one on the Refiner Libraries settings page, then queue this work again.");
                }
                else
                {
                    (runtime, problem) = RemuxPassPaths.RuntimeForLibrary(library, _options.WeirHome);
                }

                if (problem is not null)
                {
                    return new Claim(new PyDict()
                        .Set("job_id", context.Id)
                        .Set("ok", false)
                        .Set("outcome", RemuxPassOutcomes.FailedBeforeExecution)
                        .Set("reason", problem)
                        .Set("relative_media_path", rel)
                        .Set("library_id", library?.Id ?? libraryId));
                }

                if (library is not null)
                {
                    await RemuxPassFileState.MarkFileStatusAsync(uow, library.Id, rel, RefinerFileStatuses.Processing, "Refiner has claimed this file and is checking it now.", _time.GetUtcNow())
                        .ConfigureAwait(false);
                }

                return new Claim(null, operatorSettings, library, rules, runtime);
            },
            _logger,
            "claim processing file",
            cancellationToken);

    /// <summary><c>resolve_library</c>: by id when the payload carries one, else the seeded library for its scope.</summary>
    public static async Task<RefinerLibraryRecord?> ResolveLibraryAsync(UnitOfWork uow, long? libraryId, string? mediaScope)
    {
        if (libraryId is { } id && await LibraryStore.GetAsync(uow, id).ConfigureAwait(false) is { } found)
        {
            return found;
        }

        return await LibraryStore.SeededForScopeAsync(uow, mediaScope ?? "movie").ConfigureAwait(false);
    }

    private static async Task<RefinerRulesConfig?> RulesConfigForAsync(UnitOfWork uow, RefinerLibraryRecord library) =>
        library.RuleSetId is { } ruleSetId && await LibraryStore.GetRuleSetAsync(uow, ruleSetId).ConfigureAwait(false) is { } ruleSet
            ? RemuxPassPaths.RulesConfigFor(ruleSet)
            : null;

    /// <summary><c>load_refiner_remux_rules_config</c>: the seeded library's rule set for the scope, or the shipped defaults.</summary>
    private static async Task<RefinerRulesConfig> LoadScopeRulesConfigAsync(UnitOfWork uow, string mediaScope)
    {
        var seeded = await LibraryStore.SeededForScopeAsync(uow, mediaScope).ConfigureAwait(false);
        var ruleSet = seeded?.RuleSetId is { } id ? await LibraryStore.GetRuleSetAsync(uow, id).ConfigureAwait(false) : null;
        return RuleSetConversion.ToRulesConfig(ruleSet);
    }

    private async Task<PyDict?> CarriedOriginAsync(long jobId, long? libraryId, string rel, string mediaScope)
    {
        try
        {
            var uow = await UnitOfWork.OpenAsync(_database).ConfigureAwait(false);
            await using (uow.ConfigureAwait(false))
            {
                var library = await ResolveLibraryAsync(uow, libraryId, mediaScope).ConfigureAwait(false);
                return await HandoffOriginCarry.FindAsync(uow, library?.Id ?? libraryId, rel, jobId).ConfigureAwait(false);
            }
        }
        catch (Exception exception) when (exception is SqliteException or InvalidOperationException)
        {
            _logger.LogWarning(exception, "Refiner could not look up the hand-off this file came from.");
            return null;
        }
    }

    /// <summary><c>_apply_file_outcome_state</c>: keep the durable Files row in step with the result shown in Activity.</summary>
    internal async Task ApplyFileOutcomeStateAsync(PyDict result, long? libraryId, string mediaScope, PyDict? origin)
    {
        if (result.Get("relative_media_path") is not PyStr relValue || PyStrings.Strip(relValue.Value).Length == 0)
        {
            return;
        }

        var rel = PyStrings.Strip(relValue.Value);
        var updates = new PyDict();
        try
        {
            await LockedWrites.RunAsync(
                _database,
                async uow =>
                {
                    updates = new PyDict();
                    var library = await ResolveLibraryAsync(uow, libraryId, mediaScope).ConfigureAwait(false);
                    if (library is null)
                    {
                        return;
                    }

                    var now = _time.GetUtcNow();
                    if (result.Get("rejection_kind") is { IsTruthy: true })
                    {
                        var rejectionReason = PyStrings.Slice(CollapseWhitespace(TextOr(result.Get("reason"), "Refiner rejected this file before processing.")), 1200);
                        var cleanupDetail = TextOr(result.Get("rejected_cleanup_detail"), "The saved rejected-file action has not run yet.");
                        if (await _failurePolicy.RejectBadReleaseAsync(uow, library, rel, rejectionReason, origin).ConfigureAwait(false))
                        {
                            updates.Set("reject_queued", true);
                            cleanupDetail = "Weir is telling your media manager this release is bad so it can find a different one, " +
                                            "and removes the download only once the manager accepts.";
                        }

                        var reason = $"{rejectionReason} {cleanupDetail}";
                        if (await RemuxPassFileState.MarkFileStatusAsync(uow, library.Id, rel, RefinerFileStatuses.Skipped, reason, now).ConfigureAwait(false))
                        {
                            await RemuxPassFileState.ClearFailureFieldsAsync(uow, library.Id, rel).ConfigureAwait(false);
                        }

                        updates.Set("retry_scheduled", false).Set("quarantined", false).Set("failure_next_retry_at", PyNull.Instance).Set("failure_operator_message", reason);
                        return;
                    }

                    if (result.Get("retryable_wait") is PyBool { Value: true })
                    {
                        var reason = PyStrings.Slice(CollapseWhitespace(TextOr(result.Get("reason"), "Weir is waiting until no other program is writing this file.")), 1200);
                        if (await RemuxPassFileState.MarkFileStatusAsync(uow, library.Id, rel, RefinerFileStatuses.OnHold, reason, now).ConfigureAwait(false))
                        {
                            await RemuxPassFileState.ClearFailureFieldsAsync(uow, library.Id, rel).ConfigureAwait(false);
                        }

                        updates.Set("retry_scheduled", false).Set("quarantined", false).Set("failure_next_retry_at", PyNull.Instance).Set("failure_operator_message", reason);
                        return;
                    }

                    if (result.Get("ok") is PyBool { Value: false })
                    {
                        var failureClass = RefinerFailureClasses.Classify(TextOr(result.Get("outcome"), string.Empty));
                        var reason = PyStrings.Slice(CollapseWhitespace(TextOr(result.Get("reason"), "Refiner returned an unsuccessful result.")), 1200);
                        var decision = await RemuxPassFileState.RecordFailureAsync(uow, library, rel, failureClass, reason, now).ConfigureAwait(false);
                        var followUp = await _failurePolicy.ApplyFailurePolicyAsync(
                            uow, library, rel, decision.WillRetry, origin, result.Get("content_unusable") is PyBool { Value: true }).ConfigureAwait(false);
                        updates
                            .Set("pass_through_queued", followUp == RefinerFailurePolicies.PassThrough)
                            .Set("reject_queued", followUp == RefinerFailurePolicies.Reject)
                            .Set("failure_class", failureClass)
                            .Set("retry_scheduled", decision.WillRetry)
                            .Set("quarantined", decision.Quarantined)
                            .Set("failure_next_retry_at", decision.NextRetryAt is { } next ? PyDateTime.FromDateTimeOffset(next).IsoFormat() : null)
                            .Set("failure_operator_message", decision.Reason);
                        return;
                    }

                    var processedReason = result.Get("pass_through_unchanged") is PyBool { Value: true }
                        ? "Weir passed this file through unchanged at the operator's request and placed it in the output folder."
                        : result.Get("outcome") is PyStr { Value: RemuxPassOutcomes.LiveSkippedNotRequired }
                            ? "Refiner checked this file and found that no changes were needed."
                            : "Refiner finished processing this file.";
                    if (await RemuxPassFileState.MarkFileStatusAsync(uow, library.Id, rel, RefinerFileStatuses.Processed, processedReason, now).ConfigureAwait(false))
                    {
                        await RemuxPassFileState.ClearFailureFieldsAsync(uow, library.Id, rel).ConfigureAwait(false);
                    }
                },
                _logger,
                "file outcome").ConfigureAwait(false);
            foreach (var (key, value) in updates.Items)
            {
                result.Set(key, value);
            }
        }
        catch (Exception exception) when (exception is SqliteException or InvalidOperationException)
        {
            // The media pass remains the source of truth; a false failure over a completed file would be worse.
            _logger.LogWarning(exception, "Refiner could not save the durable Files state; inspect the processing record.");
        }
    }

    /// <summary><c>_record_failed_result</c>: preflight failures through the same Files/Activity contract as a run result.</summary>
    private async Task RecordFailedResultAsync(PyDict payload, long? libraryId, string mediaScope, PyDict? origin)
    {
        await ApplyFileOutcomeStateAsync(payload, libraryId, mediaScope, origin).ConfigureAwait(false);
        await RecordAsync(payload).ConfigureAwait(false);
    }

    /// <summary>
    /// <c>_record</c>: the processing record and the Activity row, written together so they cannot disagree. A progress row
    /// already started for the pass becomes the completed row.
    /// </summary>
    internal async Task RecordAsync(PyDict payload, long? activityId = null)
    {
        var detail = RemuxPassVisibility.ActivityDetail(payload);
        var title = RemuxPassVisibility.ActivityTitle(payload);
        try
        {
            await LockedWrites.RunAsync(
                _database,
                async uow =>
                {
                    if (payload.Get("relative_media_path") is PyStr rel && PyStrings.Strip(rel.Value).Length > 0)
                    {
                        try
                        {
                            await RemuxPassFileState.RecordFileLogAsync(uow, rel.Value, title, payload, _time.GetUtcNow()).ConfigureAwait(false);
                        }
                        catch (SqliteException exception) when (LockedWrites.IsLock(exception))
                        {
                            throw;
                        }
                        catch (Exception exception) when (exception is SqliteException or InvalidOperationException)
                        {
                            _logger.LogError(exception, "Refiner could not write the processing record for {Path}.", rel.Value);
                        }
                    }

                    if (activityId is { } id &&
                        await SqliteActivityWriter.UpdateAsync(uow, id, ActivityEventTypes.RefinerFileRemuxPassCompleted, title, detail).ConfigureAwait(false))
                    {
                        return;
                    }

                    await SqliteActivityWriter.RecordAsync(uow, new ActivityEventDraft(ActivityEventTypes.RefinerFileRemuxPassCompleted, "refiner", title, detail))
                        .ConfigureAwait(false);
                },
                _logger,
                "processing record").ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is SqliteException or InvalidOperationException)
        {
            // Activity is observability, never a prerequisite for a safe media mutation.
            _logger.LogWarning(exception, "Refiner could not save the processing record; the pass result remains authoritative.");
        }
    }

    /// <summary><c>_finish_rejected_input_cleanup</c>: an opt-in rejection deletion, applied after the rejection was recorded.</summary>
    private async Task FinishRejectedInputCleanupAsync(PyDict result, long? libraryId, string mediaScope)
    {
        if (result.Get("rejection_kind") is not { IsTruthy: true } || result.Get("rejected_file_action") is not PyStr { Value: "delete_file" })
        {
            return;
        }

        if (result.Get("refiner_watched_folder_resolved") is not PyStr watched || result.Get("inspected_source_path") is not PyStr inspected)
        {
            result.Set("rejected_cleanup_status", "not_deleted");
            result.Set("rejected_cleanup_detail", "Weir did not delete the rejected file because its verified watched-folder path was unavailable.");
        }
        else
        {
            var cleanup = RemuxPassPaths.CleanupRejectedFile(watched.Value, inspected.Value, "delete_file");
            result.Set("rejected_cleanup_status", cleanup.Deleted ? "deleted" : "not_deleted");
            result.Set("rejected_cleanup_detail", cleanup.Detail);
        }

        await ApplyFileOutcomeStateAsync(result, libraryId, mediaScope, null).ConfigureAwait(false);
        if (result.Get("relative_media_path") is not PyStr rel || PyStrings.Strip(rel.Value).Length == 0)
        {
            return;
        }

        await LockedWrites.RunAsync(
            _database,
            uow => RemuxPassFileState.RecordFileLogAsync(uow, rel.Value, "Rejected file cleanup finished", result, _time.GetUtcNow()),
            _logger,
            "rejected file cleanup record").ConfigureAwait(false);
    }

    /// <summary><c>_report_back</c>: tell the originating manager how the pass went. Best effort; never throws.</summary>
    private async Task ReportBackAsync(string? payloadJson, PyDict result)
    {
        if (_reporter is null)
        {
            return;
        }

        try
        {
            var uow = await UnitOfWork.OpenAsync(_database).ConfigureAwait(false);
            await using (uow.ConfigureAwait(false))
            {
                var status = await _reporter.ReportHandoffCompletionAsync(uow, payloadJson, result).ConfigureAwait(false);
                if (!status.StartsWith("skipped", StringComparison.Ordinal))
                {
                    _logger.LogInformation("Refiner hand-off callback: {Status}", status);
                }
            }
        }
#pragma warning disable CA1031 // Reporting must never break the job.
        catch (Exception exception)
#pragma warning restore CA1031
        {
            _logger.LogError(exception, "Refiner hand-off callback raised unexpectedly.");
        }
    }

    private static PyDict FailedPayload(long jobId, string reason) => new PyDict()
        .Set("job_id", jobId)
        .Set("ok", false)
        .Set("outcome", RemuxPassOutcomes.FailedBeforeExecution)
        .Set("reason", reason);

    /// <summary><c>d.update(other)</c>.</summary>
    private static PyDict Merge(PyDict target, PyDict other)
    {
        foreach (var (key, value) in other.Items)
        {
            target.Set(key, value);
        }

        return target;
    }

    /// <summary><c>str(value or fallback)</c>.</summary>
    private static string TextOr(PyJson? value, string fallback) => value is { IsTruthy: true } ? PyConvert.Str(value) : fallback;

    /// <summary><c>" ".join(text.split())</c>.</summary>
    private static string CollapseWhitespace(string text) =>
        string.Join(' ', text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
}

/// <summary>
/// <c>RefinerActivityProgressReporter</c>: one live <c>refiner.file_processing_progress</c> row per pass, inserted on the first
/// update and rewritten after. A failed write never interrupts ffprobe or ffmpeg.
/// </summary>
public sealed class ActivityProgressReporter
{
    private readonly SqliteDatabase _database;
    private readonly long _jobId;
    private readonly PyDict _extra;
    private readonly ILogger _logger;
    private readonly Lock _lock = new();

    public ActivityProgressReporter(SqliteDatabase database, long jobId, PyDict extra, ILogger logger)
    {
        _database = database ?? throw new ArgumentNullException(nameof(database));
        _jobId = jobId;
        _extra = extra ?? new PyDict();
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <summary>The progress row, once written; the handler turns it into the completed row.</summary>
    public long? ActivityId { get; private set; }

    public void Report(PyDict payload)
    {
        ArgumentNullException.ThrowIfNull(payload);
        var body = new PyDict().Set("job_id", _jobId);
        foreach (var (key, value) in _extra.Items.Concat(payload.Items))
        {
            body.Set(key, value);
        }

        lock (_lock)
        {
            var delay = TimeSpan.FromSeconds(0.1);
            for (var attempt = 0; attempt < 4; attempt++)
            {
                try
                {
                    Write(body);
                    return;
                }
                catch (SqliteException exception) when (LockedWrites.IsLock(exception) && attempt < 3)
                {
                    Thread.Sleep(delay);
                    delay *= 2;
                }
#pragma warning disable CA1031 // A progress update must never interrupt the media pass.
                catch (Exception exception)
#pragma warning restore CA1031
                {
                    _logger.LogWarning(exception, "Refiner could not save a progress update; continuing the media pass.");
                    return;
                }
            }
        }
    }

    private void Write(PyDict body)
    {
        using var connection = _database.Open();
        using var transaction = connection.BeginTransaction(deferred: false);
        var name = FileName(body.Get("relative_media_path"));
        var detail = PyStrings.Slice(PyJsonWriter.Dumps(body, PyJsonFormat.Compact), 6000);
        if (ActivityId is null)
        {
            var id = SqliteActivityWriter.Record(connection, transaction, new ActivityEventDraft(ActivityEventTypes.RefinerFileProcessingProgress, "refiner", $"Refiner is processing {name}", detail));
            transaction.Commit();
            ActivityNotifications.TransactionCommitted(_database, transaction);
            ActivityId = id;
            return;
        }

        var title = (body.Get("status") is { IsTruthy: true } status ? PyConvert.Str(status) : "processing") switch
        {
            "waiting" => $"Waiting to process {name}",
            "finishing" => $"Refiner is finishing {name}",
            "finished" => $"{name} finished processing",
            "failed" => $"{name} could not be processed",
            _ => $"Refiner is processing {name}",
        };
        SqliteActivityWriter.Update(connection, transaction, ActivityId.Value, title: title, detail: detail);
        transaction.Commit();
        ActivityNotifications.TransactionCommitted(_database, transaction);
    }

    /// <summary><c>Path(str(relative_media_path or "")).name or "this file"</c>.</summary>
    private static string FileName(PyJson? value)
    {
        var text = value is { IsTruthy: true } ? PyConvert.Str(value) : string.Empty;
        var name = MediaPathNames.Name(text, OperatingSystem.IsWindows());
        return name.Length > 0 ? name : "this file";
    }
}
