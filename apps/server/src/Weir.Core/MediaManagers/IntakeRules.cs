using System.Text.RegularExpressions;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.Rules;

namespace Weir.Core.MediaManagers;

/// <summary>The library columns intake reads.</summary>
public sealed record IntakeLibrary(long Id, string MediaType, string WatchedFolder);

/// <summary>The rules of <c>intake_api</c> that do not touch the database or filesystem.</summary>
public static partial class IntakeRules
{
    /// <summary><c>PROCESSING_FILE_REMUX_PASS_JOB_KIND</c>.</summary>
    public const string RemuxPassJobKind = "processing.file.remux_pass.v1";

    /// <summary><c>PROCESSING_FILE_PASS_THROUGH_JOB_KIND</c>.</summary>
    public const string PassThroughJobKind = "processing.file.pass_through.v1";

    /// <summary><c>PROCESSING_FILE_REJECT_JOB_KIND</c>.</summary>
    public const string RejectJobKind = "processing.file.reject.v1";

    public const string MissingSecretDetail = "Invalid or missing X-Webhook-Secret header.";
    public const string NeedsSecretDetail = "Set a webhook secret in Weir so a media manager can ask about hand-offs.";
    public const string NeverReceivedDetail = "Weir has never received this hand-off.";

    /// <summary><c>HANDOFF_CAPABILITIES</c>.</summary>
    public static readonly IReadOnlyList<string> HandoffCapabilities = ["handoff-status", "handoff-cancel"];

    /// <summary><c>remux_dedupe_key</c>: the remux job's key for a hand-off, exactly as intake writes it.</summary>
    public static string RemuxDedupeKey(string sourceKey, string handoffId) => $"{RemuxPassJobKind}:{sourceKey}:handoff:{handoffId}";

    /// <summary>The base key: the manager's hand-off id when it gave one, otherwise a fresh one.</summary>
    public static string BaseDedupeKey(MediaManagerImportEvent importEvent, Func<Guid> newGuid)
    {
        ArgumentNullException.ThrowIfNull(importEvent);
        ArgumentNullException.ThrowIfNull(newGuid);
        return importEvent.HandoffId is { Length: > 0 } handoffId
            ? RemuxDedupeKey(importEvent.SourceKey, handoffId)
            : $"{RemuxPassJobKind}:{newGuid():N}";
    }

    /// <summary>One file keeps the plain key; a folder's files are keyed apart so each runs once.</summary>
    public static string DedupeKeyFor(string baseKey, IReadOnlyList<string> targets, string target, string resolvedRelativePath)
    {
        ArgumentNullException.ThrowIfNull(targets);
        return targets.Count == 1 && target == resolvedRelativePath ? baseKey : $"{baseKey}:{target}";
    }

    /// <summary>The job payload intake writes, with <paramref name="target"/> as its <c>relative_media_path</c>.</summary>
    public static PyDict Payload(MediaManagerImportEvent importEvent, IntakeLibrary? library, string? resolvedRelativePath, string target)
    {
        ArgumentNullException.ThrowIfNull(importEvent);
        var payload = new PyDict()
            .Set("relative_media_path", resolvedRelativePath)
            .Set("media_scope", library is not null ? library.MediaType : importEvent.MediaScope)
            .Set("trigger", "webhook");
        if (library is not null)
        {
            payload.Set("library_id", library.Id);
        }

        if (!string.IsNullOrEmpty(importEvent.HandoffId) || !string.IsNullOrEmpty(importEvent.CallbackPath))
        {
            payload.Set("origin", new PyDict()
                .Set("source_key", importEvent.SourceKey)
                .Set("handoff_id", importEvent.HandoffId)
                .Set("callback_path", importEvent.CallbackPath)
                .Set("release_name", importEvent.ReleaseName)
                .Set("library_id", importEvent.LibraryId));
        }

        payload.Set("relative_media_path", target);
        return payload;
    }

    /// <summary>The payload as Python's <c>json.dumps(payload, separators=(",", ":"))</c> writes it.</summary>
    public static string PayloadJson(PyDict payload) => PyJsonWriter.Dumps(payload, PyJsonFormat.Compact);

    /// <summary>
    /// <c>_library_for_handoff</c>'s choice among libraries whose watched folder holds the file: a library of the
    /// hand-off's media type first, then the deepest folder, then the lowest id. Null when none holds it.
    /// </summary>
    public static (IntakeLibrary Library, HandoffPathResult Resolved)? ChooseLibrary(IEnumerable<IntakeLibrary> libraries, MediaManagerImportEvent importEvent)
    {
        ArgumentNullException.ThrowIfNull(libraries);
        ArgumentNullException.ThrowIfNull(importEvent);
        (IntakeLibrary Library, HandoffPathResult Resolved, bool SameType, int Depth)? best = null;
        foreach (var library in libraries)
        {
            var resolved = HandoffPaths.RelativeMediaPathForHandoff(library.WatchedFolder, importEvent.FilePath);
            if (!resolved.Ok)
            {
                continue;
            }

            var depth = library.WatchedFolder.Replace('\\', '/').Split('/').Count(part => part.Length > 0);
            var sameType = library.MediaType == importEvent.MediaScope;
            if (best is not { } current ||
                (sameType, depth, -library.Id).CompareTo((current.SameType, current.Depth, -current.Library.Id)) > 0)
            {
                best = (library, resolved, sameType, depth);
            }
        }

        return best is { } chosen ? (chosen.Library, chosen.Resolved) : null;
    }

    /// <summary><c>_SAMPLE_PART</c>: a path part that is, or contains the word, "sample".</summary>
    [GeneratedRegex("(^|[^a-z0-9])sample([^a-z0-9]|$)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    public static partial Regex SamplePart();

    /// <summary><c>is_processing_media_candidate</c> on a name: the pathlib suffix, lower-cased, in the allowlist.</summary>
    public static bool IsMediaCandidateName(string fileName) =>
        RemuxRules.MediaExtensions.Contains(MediaPathNames.Suffix(fileName, windows: false).ToLowerInvariant());

    /// <summary>
    /// Which of a folder's videos a hand-off means (relative parts under the folder, in pathlib order): the ones with
    /// no sample part, or every video when all of them are samples.
    /// </summary>
    public static List<IReadOnlyList<string>> ChooseFolderVideos(IEnumerable<IReadOnlyList<string>> videoParts, bool windows)
    {
        ArgumentNullException.ThrowIfNull(videoParts);
        var videos = videoParts.ToList();
        videos.Sort((a, b) => ComparePathParts(a, b, windows));
        var main = videos.Where(parts => !parts.Any(part => SamplePart().IsMatch(part))).ToList();
        return main.Count > 0 ? main : videos;
    }

    /// <summary>pathlib's ordering: part by part, case-folded on Windows.</summary>
    public static int ComparePathParts(IReadOnlyList<string> left, IReadOnlyList<string> right, bool windows)
    {
        ArgumentNullException.ThrowIfNull(left);
        ArgumentNullException.ThrowIfNull(right);
        for (var i = 0; i < Math.Min(left.Count, right.Count); i++)
        {
            var a = windows ? left[i].ToLowerInvariant() : left[i];
            var b = windows ? right[i].ToLowerInvariant() : right[i];
            var compared = string.CompareOrdinal(a, b);
            if (compared != 0)
            {
                return compared;
            }
        }

        return left.Count.CompareTo(right.Count);
    }

    public static string NoVideoInFolderDetail(string relativePath) =>
        $"The hand-off names the folder {PyStrings.Repr(relativePath)}, but it holds no video file Weir processes. Nothing was queued.";

    public static string UnknownSourceDetail(string sourceKey) =>
        $"Unknown media manager source {PyStrings.Repr(sourceKey)}. Known sources: {string.Join(", ", ImportEvents.KnownSourceKeys())}. " +
        "Use 'native' for a manager without a dialect of its own.";

    public static string UnknownSourceShortDetail(string sourceKey) => $"Unknown media manager source {PyStrings.Repr(sourceKey)}.";

    /// <summary>The Activity title when a manager cancels a hand-off.</summary>
    public static string CancelledTitle(string sourceKey, string relativePath, bool windows) =>
        $"{PyValues.Capitalize(sourceKey)} cancelled its hand-off of {MediaPathNames.Name(relativePath, windows)}";

    /// <summary>The Activity detail when a manager cancels a hand-off.</summary>
    public static string CancelledDetail(string sourceKey, string handoffId, string relativePath, long? libraryId, string sentence) =>
        PyJsonWriter.Dumps(
            new PyDict()
                .Set("source", sourceKey)
                .Set("handoff_id", handoffId)
                .Set("relative_media_path", relativePath)
                .Set("library_id", libraryId)
                .Set("trigger", "webhook")
                .Set("result", "success")
                .Set("message", sentence),
            PyJsonFormat.Compact);

    public static string RefusedCancelSentence(string state) => $"This hand-off is {state}, so Weir did not cancel it.";
}
