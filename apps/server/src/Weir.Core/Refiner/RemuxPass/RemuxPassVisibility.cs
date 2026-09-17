using System.Globalization;
using Weir.Core.Activity;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.Observability;
using Weir.Core.Rules;

namespace Weir.Core.Refiner.RemuxPass;

/// <summary>The job kind and outcomes of one per-file pass (<c>file_remux_pass/job_kinds.py</c> and <c>visibility.py</c>).</summary>
public static class RemuxPassOutcomes
{
    /// <summary><c>REFINER_FILE_REMUX_PASS_JOB_KIND</c>.</summary>
    public const string JobKind = "refiner.file.remux_pass.v1";

    public const string LiveOutputWritten = "live_output_written";
    public const string LiveSkippedNotRequired = "live_skipped_not_required";
    public const string SkippedGuardrail = "skipped_guardrail";
    public const string SourceNotReady = "source_not_ready";
    public const string FailedBeforeExecution = "failed_before_execution";
    public const string FailedDuringExecution = "failed_during_execution";
}

/// <summary>Operator-facing strings for a pass (port of <c>file_remux_pass/visibility.py</c>).</summary>
public static class RemuxPassVisibility
{
    private const int MaxArgvForActivity = 64;

    /// <summary><c>summarize_remux_plan</c>: a compact plan summary, not a full ffmpeg command.</summary>
    public static string SummarizeRemuxPlan(RemuxPlan plan, int maxLength = 600)
    {
        ArgumentNullException.ThrowIfNull(plan);
        var audio = plan.Audio.Count == 0 ? "none" : string.Join(", ", plan.Audio.Select(Track));
        var subtitles = plan.Subtitles.Count == 0 ? "none" : string.Join(", ", plan.Subtitles.Select(Track));
        var removedAudio = string.Join("; ", plan.RemovedAudio.Take(6));
        if (plan.RemovedAudio.Count > 6)
        {
            removedAudio += $" (+{(plan.RemovedAudio.Count - 6).ToString(CultureInfo.InvariantCulture)} more)";
        }

        var removedSubtitles = string.Join("; ", plan.RemovedSubtitles.Take(6));
        if (plan.RemovedSubtitles.Count > 6)
        {
            removedSubtitles += $" (+{(plan.RemovedSubtitles.Count - 6).ToString(CultureInfo.InvariantCulture)} more)";
        }

        var parts = new List<string>
        {
            $"video copy indices: {PythonIntList(plan.VideoIndices)}",
            $"audio out: {audio}",
            $"subtitles out: {subtitles}",
        };
        if (removedAudio.Length > 0)
        {
            parts.Add($"removed audio: {removedAudio}");
        }

        if (removedSubtitles.Length > 0)
        {
            parts.Add($"removed subs: {removedSubtitles}");
        }

        var summary = string.Join(" | ", parts);
        return PyStrings.Length(summary) > maxLength ? PyStrings.Slice(summary, maxLength - 12) + "…(truncated)" : summary;

        static string Track(PlannedTrack track) =>
            $"#{track.InputIndex.ToString(CultureInfo.InvariantCulture)} {(track.LangLabel.Length > 0 ? track.LangLabel : "und")}";
    }

    /// <summary>Python's <c>repr</c> of a list of ints: <c>[0, 2]</c>.</summary>
    public static string PythonIntList(IEnumerable<int> values) =>
        "[" + string.Join(", ", values.Select(v => v.ToString(CultureInfo.InvariantCulture))) + "]";

    /// <summary><c>remux_pass_activity_title</c>: one plain line, with the file name when there is one.</summary>
    public static string ActivityTitle(PyDict payload)
    {
        ArgumentNullException.ThrowIfNull(payload);
        var name = payload.Get("relative_media_path") is PyStr rel && PyStrings.Strip(rel.Value).Length > 0
            ? MediaPathNames.Name(rel.Value, OperatingSystem.IsWindows())
            : "unknown file";
        var outcome = payload.Get("outcome") is PyStr text ? text.Value : null;
        if (payload.Get("pass_through_unchanged") is PyBool { Value: true } && outcome == RemuxPassOutcomes.LiveSkippedNotRequired)
        {
            return $"{name} was passed through unchanged";
        }

        return outcome switch
        {
            RemuxPassOutcomes.LiveOutputWritten => $"{name} was processed successfully",
            RemuxPassOutcomes.LiveSkippedNotRequired => $"No changes needed for {name}",
            RemuxPassOutcomes.SkippedGuardrail => $"Skipped {name}",
            RemuxPassOutcomes.SourceNotReady => $"Waiting for {name}",
            RemuxPassOutcomes.FailedDuringExecution => $"{name} could not be processed",
            _ when outcome == RemuxPassOutcomes.FailedBeforeExecution || payload.Get("ok") is PyBool { Value: false } => $"{name} could not be checked",
            _ => "Refiner file processing finished",
        };
    }

    /// <summary>
    /// <c>clip_remux_pass_payload_for_activity</c>: the diagnostic envelope, and the ffmpeg argv bounded so Activity JSON
    /// stays under typical row limits.
    /// </summary>
    public static PyDict ClipForActivity(PyDict payload)
    {
        ArgumentNullException.ThrowIfNull(payload);
        var output = payload.Copy();
        var outcome = output.Get("outcome") is { IsTruthy: true } value ? PyConvert.Str(value) : string.Empty;
        string result;
        if (outcome is RemuxPassOutcomes.LiveOutputWritten or RemuxPassOutcomes.LiveSkippedNotRequired)
        {
            result = "success";
        }
        else if (outcome is RemuxPassOutcomes.SkippedGuardrail or RemuxPassOutcomes.SourceNotReady)
        {
            result = "skipped";
        }
        else
        {
            result = output.Get("ok") is PyBool { Value: false } ? "failed" : "success";
        }

        if (result == "failed" && output.Get("retry_scheduled") is PyBool { Value: true })
        {
            // Not the end of it: the standard calls a failure that will be tried again "retrying".
            result = "retrying";
        }

        var trigger = output.Get("trigger") is PyStr rawTrigger && ActivityClassifier.Triggers.Contains(rawTrigger.Value) ? rawTrigger.Value : "worker";
        string? nextAction = null;
        if (result == "failed" && !(Truthy(output.Get("pass_through_queued")) || Truthy(output.Get("reject_queued"))))
        {
            // The reason stays in the detail; an action is something the operator can do.
            nextAction = "Open this file's processing record for what went wrong, fix the cause, then use Try again on the Files screen.";
        }

        var envelope = OperatorMessages.ActivityDetailEnvelope(
            module: "refiner",
            action: "remux",
            trigger: trigger,
            result: result,
            mediaScope: output.Get("media_scope") is PyStr scope ? scope.Value : null,
            counts:
            [
                new("audio_removed", ListLength(output.Get("removed_audio"))),
                new("subtitles_removed", ListLength(output.Get("removed_subtitles"))),
            ],
            userMessage: ActivityTitle(output),
            nextAction: nextAction);
        foreach (var (key, item) in envelope.Items)
        {
            output.Set(key, item);
        }

        if (output.Get("ffmpeg_argv") is PyList { Items.Count: > MaxArgvForActivity } argv)
        {
            var clipped = new PyList(argv.Items.Take(MaxArgvForActivity));
            clipped.Items.Add(new PyStr("…(truncated for activity log)"));
            output.Set("ffmpeg_argv", clipped);
            output.Set("ffmpeg_argv_truncated", true);
        }

        return output;
    }

    /// <summary><c>remux_pass_result_to_activity_detail</c>: the clipped payload as ASCII JSON, cut at 10,000 characters.</summary>
    public static string ActivityDetail(PyDict payload, int maxChars = 10_000) =>
        PyStrings.Slice(PyJsonWriter.Dumps(ClipForActivity(payload), PyJsonFormat.Compact), maxChars);

    /// <summary>Python truthiness of an optional value (<c>bool(d.get(key))</c>).</summary>
    public static bool Truthy(PyJson? value) => value is not null && value.IsTruthy;

    /// <summary><c>len(value or [])</c> for a list-valued key.</summary>
    private static long ListLength(PyJson? value) => value switch
    {
        PyList list => list.Items.Count,
        PyStr text => PyStrings.Length(text.Value),
        PyDict dict => dict.Count,
        _ => 0,
    };
}
