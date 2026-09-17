using Weir.Core.Json;

namespace Weir.Core.MediaManagers;

/// <summary>The manager-supplied half of a hand-off, carried on the job payload (<c>HandoffOrigin</c>).</summary>
public sealed record HandoffOrigin(string SourceKey, string? HandoffId, string? CallbackPath, string? ReleaseName, string? LibraryId = null)
{
    /// <summary><c>HandoffOrigin.from_payload</c>: null unless the payload has an origin naming its source.</summary>
    public static HandoffOrigin? FromPayload(PyJson? payload)
    {
        if (payload is not PyDict dict || dict.Get("origin") is not PyDict origin)
        {
            return null;
        }

        var sourceKey = PyStrings.Strip(Truthy(origin.Get("source_key")) is { } value ? PyConvert.Str(value) : string.Empty);
        if (sourceKey.Length == 0)
        {
            return null;
        }

        return new HandoffOrigin(
            sourceKey,
            OptionalText(origin.Get("handoff_id")),
            OptionalText(origin.Get("callback_path")),
            OptionalText(origin.Get("release_name")),
            OptionalText(origin.Get("library_id")));
    }

    /// <summary><c>_optional_text</c>: <c>str(value).strip()</c> of a truthy value, or null.</summary>
    public static string? OptionalText(PyJson? value)
    {
        if (Truthy(value) is not { } present)
        {
            return null;
        }

        var text = PyStrings.Strip(PyConvert.Str(present));
        return text.Length == 0 ? null : text;
    }

    private static PyJson? Truthy(PyJson? value) => value is not null && value.IsTruthy ? value : null;
}

/// <summary>Whether a manager accepted a report. <see cref="Accepted"/> is only ever true on a 2xx answer.</summary>
public sealed record HandoffReportDelivery(bool Accepted, string Status);

/// <summary>The report body and its wording (port of the pure parts of <c>completion_callback</c>).</summary>
public static class CompletionReports
{
    public const string ProcessorName = "Weir";

    public const string PassThroughAfterFailureMessage =
        "Weir could not process this file, so it handed the original back unchanged; it is ready to import.";

    public static readonly TimeSpan Timeout = TimeSpan.FromSeconds(20);

    private static readonly HashSet<string> SuccessOutcomes = new(StringComparer.Ordinal) { "live_output_written", "live_skipped_not_required" };

    private static string Outcome(PyDict result) =>
        PyStrings.Strip(result.Get("outcome") is { IsTruthy: true } value ? PyConvert.Str(value) : string.Empty);

    /// <summary><c>is_succeeded</c>: <c>ok</c> and an outcome that actually wrote or verified a file.</summary>
    public static bool IsSucceeded(PyDict result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return result.Get("ok") is { IsTruthy: true } && SuccessOutcomes.Contains(Outcome(result));
    }

    /// <summary><c>build_completion_body</c>.</summary>
    public static PyDict BuildCompletionBody(HandoffOrigin origin, PyDict result, string? outputPath = null, bool rejected = false)
    {
        ArgumentNullException.ThrowIfNull(origin);
        ArgumentNullException.ThrowIfNull(result);
        var outcome = Outcome(result);
        var succeeded = IsSucceeded(result);
        var body = new PyDict()
            .Set("handoffId", origin.HandoffId)
            .Set("status", succeeded ? "completed" : "failed")
            .Set("processorName", ProcessorName);
        if (!string.IsNullOrEmpty(origin.LibraryId))
        {
            body.Set("libraryId", origin.LibraryId);
        }

        if (!string.IsNullOrEmpty(origin.ReleaseName))
        {
            body.Set("releaseName", origin.ReleaseName);
        }

        if (succeeded)
        {
            PyJson? outputFile = !string.IsNullOrEmpty(outputPath) ? new PyStr(outputPath) : result.Get("output_file");
            if (outputFile is PyStr file && PyStrings.Strip(file.Value).Length > 0)
            {
                body.Set("outputPath", PyStrings.Strip(file.Value));
            }

            body.Set("message", SuccessMessage(outcome, result));
        }
        else
        {
            body.Set("message", FailureMessage(result));
            if (rejected)
            {
                body.Set("disposition", "rejected");
                body.Set("sourceRemoved", true);
            }
            else if (result.Get("rejected_cleanup_status") is PyStr { Value: "deleted" })
            {
                body.Set("sourceRemoved", true);
            }
            else
            {
                body.Set("disposition", "held");
                body.Set("sourceRemoved", false);
            }

            if (result.Get("failure_class") is PyStr failureClass && PyStrings.Strip(failureClass.Value).Length > 0)
            {
                body.Set("failureClass", PyStrings.Strip(failureClass.Value));
            }
        }

        return body;
    }

    private static string SuccessMessage(string outcome, PyDict result)
    {
        if (result.Get("passed_through_after_failure") is PyBool { Value: true })
        {
            return PassThroughAfterFailureMessage;
        }

        if (result.Get("pass_through_unchanged") is PyBool { Value: true })
        {
            return "The operator passed this file through unchanged; it is ready in the output folder.";
        }

        if (outcome == "live_skipped_not_required")
        {
            return "No remux was needed; the file was already in the wanted shape.";
        }

        var parts = new List<string>();
        if (result.Get("removed_audio") is PyList { Items.Count: > 0 } audio)
        {
            parts.Add($"{audio.Items.Count} audio track(s)");
        }

        if (result.Get("removed_subtitles") is PyList { Items.Count: > 0 } subtitles)
        {
            parts.Add($"{subtitles.Items.Count} subtitle track(s)");
        }

        return parts.Count == 0 ? "Remux finished." : "Removed " + string.Join(" and ", parts) + ".";
    }

    private static string FailureMessage(PyDict result)
    {
        foreach (var key in new[] { "reason", "output_completeness_note", "source_folder_skip_reason" })
        {
            if (result.Get(key) is PyStr text && PyStrings.Strip(text.Value).Length > 0)
            {
                return PyStrings.Strip(text.Value);
            }
        }

        return "The processing pass did not produce a usable output.";
    }

    /// <summary>
    /// <c>str(_pure_manager_path(folder).joinpath(*parts))</c>: the path in the manager's own style, since its host
    /// is not necessarily this one.
    /// </summary>
    public static string ManagerPathJoin(string managerFolder, IEnumerable<string> parts)
    {
        ArgumentNullException.ThrowIfNull(managerFolder);
        var text = PyStrings.Strip(managerFolder);
        var windows = text.Contains('\\', StringComparison.Ordinal) || (text.Length >= 2 && text[1] == ':' && char.IsLetter(text[0]));
        var separator = windows ? '\\' : '/';
        var normalized = windows ? text.Replace('/', '\\') : text;
        string anchor;
        string rest;
        if (windows)
        {
            if (normalized.StartsWith(@"\\", StringComparison.Ordinal))
            {
                var pieces = normalized[2..].Split('\\');
                var share = pieces.Length > 1 ? $@"\\{pieces[0]}\{pieces[1]}\" : @"\\" + normalized[2..];
                anchor = share;
                rest = pieces.Length > 2 ? string.Join('\\', pieces.Skip(2)) : string.Empty;
            }
            else if (normalized.Length >= 2 && normalized[1] == ':')
            {
                var rooted = normalized.Length >= 3 && normalized[2] == '\\';
                anchor = normalized[..2] + (rooted ? "\\" : string.Empty);
                rest = normalized[(rooted ? 3 : 2)..];
            }
            else if (normalized.StartsWith('\\'))
            {
                anchor = "\\";
                rest = normalized[1..];
            }
            else
            {
                anchor = string.Empty;
                rest = normalized;
            }
        }
        else if (normalized.StartsWith("//", StringComparison.Ordinal) && !normalized.StartsWith("///", StringComparison.Ordinal))
        {
            anchor = "//";
            rest = normalized[2..];
        }
        else if (normalized.StartsWith('/'))
        {
            anchor = "/";
            rest = normalized.TrimStart('/');
        }
        else
        {
            anchor = string.Empty;
            rest = normalized;
        }

        var components = rest.Split(separator).Concat(parts).Where(part => part.Length > 0 && part != ".").ToList();
        var joined = string.Join(separator, components);
        var result = anchor + joined;
        return result.Length == 0 ? "." : result;
    }
}
