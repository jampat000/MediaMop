using Weir.Core.Json;

namespace Weir.Core.Jobs;

/// <summary>
/// Plain-language status summaries for persisted background jobs (port of
/// <c>weir.platform.jobs.operator_job_status</c>). Job rows retain the technical error for diagnostics;
/// this is the one translation every inspection screen shares.
/// </summary>
public static class OperatorJobStatus
{
    /// <summary>
    /// Display names for module keys whose plain capitalization would not read as a person expects.
    /// The "refiner" module key is unchanged (it is the stored identifier the caller passes), but the
    /// app that runs it is just called Weir now.
    /// </summary>
    private static readonly Dictionary<string, string> ModuleDisplayNames = new(StringComparer.OrdinalIgnoreCase)
    {
        ["refiner"] = "Weir",
    };

    private static string Clean(string? raw, int limit = 1200)
    {
        var joined = string.Join(' ', (raw ?? string.Empty).Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
        return joined.Length > limit ? joined[..limit] : joined;
    }

    private static string? FileName(PyDict payload)
    {
        if (!payload.TryGetValue("relative_media_path", out var value) || value is not PyStr s || s.Value.Trim().Length == 0)
        {
            return null;
        }

        var normalized = s.Value.Replace('\\', '/');
        var slash = normalized.LastIndexOf('/');
        return slash >= 0 ? normalized[(slash + 1)..] : normalized;
    }

    /// <summary><c>build_job_operator_status</c>: (operator_message, next_action, technical_detail).</summary>
    public static (string Message, string NextAction, string? TechnicalDetail) Build(string module, string jobKind, string status, string? lastError, string? payloadJson)
    {
        _ = jobKind;
        var label = ModuleDisplayNames.TryGetValue(module, out var displayName)
            ? displayName
            : module.Length > 0 ? char.ToUpperInvariant(module[0]) + module[1..] : module;
        var payload = ParsePayload(payloadJson);
        var fileName = FileName(payload);
        var subject = fileName is not null ? $" for {fileName}" : string.Empty;
        var error = Clean(lastError, 10_000);
        var lower = error.ToLowerInvariant();
        var technical = error.Length > 0 ? error : null;

        switch (status)
        {
            case "pending":
                return ($"{label} has queued this work{subject}.", "No action is needed. Weir will start it when the required worker capacity is available.", technical);
            case "leased":
                return ($"{label} is working on this job{subject}.", "No action is needed unless it stays here beyond the normal processing time; then open the job record.", technical);
            case "completed":
                return ($"{label} finished this job{subject}.", "No action is needed. Open the processing record if you want the detailed outcome.", technical);
            case "cancelled":
                return ($"This {label} job was cancelled before a worker started it{subject}.", "No action is needed. If the file still exists and should be processed, start it again from Files.", technical);
            case "handler_ok_finalize_failed":
                return ($"The {label} work completed{subject}, but Weir could not finish saving the job result.", "Use Recover result below. Weir will not run the media work again.", technical);
        }

        if (lower.Contains("database is locked", StringComparison.Ordinal) || lower.Contains("database table is locked", StringComparison.Ordinal))
        {
            return string.Equals(module, "refiner", StringComparison.OrdinalIgnoreCase)
                ? ($"Weir could not save the result while another local operation was using the database{subject}.",
                   "Try the file again. If it repeats, set ‘Files at once’ to 1, let the current work finish, and retry.", technical)
                : ($"Weir could not save the {label} result because another local operation was using the database.",
                   "Try the job again after the current local work finishes.", technical);
        }

        if (lower.Contains("not a supported refiner media", StringComparison.Ordinal) || lower.Contains("unsupported refiner", StringComparison.Ordinal) || lower.Contains("refiner does not process", StringComparison.Ordinal) || lower.Contains("weir does not process", StringComparison.Ordinal))
        {
            return ($"This file is not a supported media file for this pass{subject}.", "Choose a supported video file or update the library’s media types, then start it again.", technical);
        }

        if (lower.Contains("could not find this file", StringComparison.Ordinal) || lower.Contains("file not found", StringComparison.Ordinal) || lower.Contains("no such file", StringComparison.Ordinal))
        {
            return ($"Weir could not find this file under the saved watched folder{subject}.", "Check the library path or restore the file, then use Start again.", technical);
        }

        if (lower.Contains("ffprobe failed", StringComparison.Ordinal) || lower.Contains("could not read this media", StringComparison.Ordinal))
        {
            return ($"Weir could not read this media file{subject}.", "Check that the file is complete and playable, then use Try again.", technical);
        }

        if (lower.Contains("legacy refiner dry_run", StringComparison.Ordinal) || lower.Contains("legacy weir dry_run", StringComparison.Ordinal))
        {
            return ($"This job was created with an older processing mode{subject}.", "Remove the old entry from the Files list, then let the next scan create a current job.", technical);
        }

        if (lower.Contains("modified too recently", StringComparison.Ordinal) || lower.Contains("still being written", StringComparison.Ordinal))
        {
            return ($"Weir is waiting for this file to finish changing{subject}.", "Wait for the copy or import to finish, then use Check again from Files.", technical);
        }

        if (lower.Contains("no retainable audio", StringComparison.Ordinal))
        {
            return ($"Weir could not build a safe audio plan for this file{subject}.", "Check the file’s audio tracks and saved audio rules, then use Try again.", technical);
        }

        if (status is "failed" or "error")
        {
            return ($"{label} could not finish this job{subject}.", "Open the related Files or Jobs screen for the explanation, fix the cause, and start it again.", technical);
        }

        return ($"{label} needs a review for this job{subject}.", "Open the related Jobs screen to inspect the current status.", technical);
    }

    private static PyDict ParsePayload(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return new PyDict();
        }

        try
        {
            return PyJsonParser.Parse(raw) as PyDict ?? new PyDict();
        }
        catch (PyJsonDecodeException)
        {
            return new PyDict();
        }
    }
}
