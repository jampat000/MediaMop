using Weir.Core.Json;
using Weir.Core.Processing;
using Weir.Core.Rules;

namespace Weir.Infrastructure.Processing.RemuxPass;

/// <summary>Resolved folders and output-side settings for one pass (<c>ProcessingPathRuntime</c>).</summary>
public sealed record ProcessingPathRuntime
{
    public required string WatchedFolder { get; init; }
    public required string OutputFolder { get; init; }
    public required string WorkFolderEffective { get; init; }
    public required bool WorkFolderIsDefault { get; init; }
    public string SidecarPatternsCsv { get; init; } = string.Empty;
    public bool PreserveOriginalTimestamps { get; init; }
    public string OutputCollisionPolicy { get; init; } = "replace";
    public string HardwareDecodeMode { get; init; } = "off";
    public string HardwareDevice { get; init; } = string.Empty;
    public string HardwareDisabledVendorsCsv { get; init; } = string.Empty;
    public string FfmpegStrictness { get; init; } = "normal";

    /// <summary>#548: which tool writes this library's output (<see cref="Weir.Core.Media.RemuxWriterChoice"/>).</summary>
    public string RemuxWriter { get; init; } = Weir.Core.Media.RemuxWriterChoice.Best;

    /// <summary>#548: rewrite with ffmpeg when the preferred writer cannot write or validate a file.</summary>
    public bool RewriteWithFfmpeg { get; init; } = true;
}

/// <summary>The rejected-file deletion's outcome (<c>RejectedFileCleanupResult</c>).</summary>
public sealed record RejectedFileCleanupResult(bool Deleted, string Detail);

/// <summary>
/// Paths for a pass: the safe join under the watched folder (<c>file_remux_pass/paths.py</c>), the library's folders
/// (<c>processing_path_settings_service.py</c>), its rules (<c>rules_config_for</c>) and the rejected-file primitive
/// (<c>processing_rejected_file_cleanup.py</c>).
/// </summary>
public static class RemuxPassPaths
{
    private static readonly bool Windows = OperatingSystem.IsWindows();

    private static StringComparison PathComparison => Windows ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;

    /// <summary><c>Path(raw).expanduser().resolve()</c> as far as .NET can: absolute and normalised.</summary>
    public static string Resolve(string raw)
    {
        var text = raw;
        if (text == "~" || text.StartsWith("~/", StringComparison.Ordinal) || text.StartsWith("~\\", StringComparison.Ordinal))
        {
            text = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) + text[1..];
        }

        var full = Path.GetFullPath(text.Length == 0 ? "." : text);
        var root = Path.GetPathRoot(full) ?? string.Empty;
        return full.Length > root.Length ? full.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) : full;
    }

    /// <summary><c>Path.relative_to</c> as a test.</summary>
    public static bool IsUnder(string path, string root) => RelativeTo(path, root) is not null;

    /// <summary>
    /// <c>path.relative_to(root)</c>: the relative part with the platform separator (empty for the root itself), or null when
    /// <paramref name="path"/> is not under <paramref name="root"/>.
    /// </summary>
    public static string? RelativeTo(string path, string root)
    {
        var p = Split(path);
        var r = Split(root);
        if (p.Count < r.Count)
        {
            return null;
        }

        for (var i = 0; i < r.Count; i++)
        {
            if (!string.Equals(p[i], r[i], PathComparison))
            {
                return null;
            }
        }

        return string.Join(Path.DirectorySeparatorChar, p.Skip(r.Count));
    }

    /// <summary>Two resolved paths name the same place.</summary>
    public static bool SamePath(string a, string b) => RelativeTo(a, b) is { Length: 0 };

    /// <summary><c>as_posix()</c> of a relative path.</summary>
    public static string Posix(string relative) => relative.Replace('\\', '/');

    private static List<string> Split(string path)
    {
        var full = Resolve(path);
        var root = Path.GetPathRoot(full) ?? string.Empty;
        var parts = new List<string> { root.TrimEnd('\\', '/').Length == 0 ? root : root.TrimEnd('\\', '/') };
        parts.AddRange(full[root.Length..].Split('\\', '/').Where(part => part.Length > 0));
        return parts;
    }

    /// <summary>
    /// <c>resolve_media_file_under_processing_root</c>: <c>(root / relative).resolve()</c>, only when it stays under the watched
    /// folder. Throws <see cref="ArgumentException"/> with the reference's sentence otherwise.
    /// </summary>
    public static string ResolveMediaFileUnderRoot(string mediaRoot, string relativePath)
    {
        var root = Resolve(mediaRoot);
        if (!Directory.Exists(root))
        {
            throw new ArgumentException("The watched folder (saved settings) must be an existing directory");
        }

        var rel = PyStrings.Strip(relativePath ?? string.Empty).Replace('\\', '/').TrimStart('/');
        if (rel.Length == 0)
        {
            throw new ArgumentException("relative_media_path is required");
        }

        if (rel.Split('/').Contains("..", StringComparer.Ordinal) || rel.StartsWith("..", StringComparison.Ordinal))
        {
            throw new ArgumentException("relative_media_path must not contain parent segments");
        }

        var candidate = Resolve(Path.Join(root, rel));
        if (!IsUnder(candidate, root))
        {
            throw new ArgumentException("resolved file path escapes the saved watched folder");
        }

        return candidate;
    }

    /// <summary><c>resolved_default_processing_work_folder</c> / <c>resolved_default_processing_tv_work_folder</c>.</summary>
    public static string DefaultWorkFolder(string weirHome, string mediaType) =>
        Path.Join(Resolve(weirHome), "processing", mediaType == "tv" ? "processing-tv-work" : "processing-movie-work");

    /// <summary>
    /// <c>effective_library_work_folder</c>: the library's own, or the per-scope default when it has
    /// none. <c>IsDefault</c> says which, and callers use it to decide whether a folder that is not on
    /// disk is an error (a custom path) or something to create (the default).
    /// </summary>
    /// <remarks>
    /// This carried the same two hard-coded MediaMop-era Windows paths as
    /// <see cref="Jobs.ProcessingLibraryFolders.EffectiveWorkFolder"/> and for the same reason; 3.0.0
    /// removed both copies. See that method for what changes for a row still holding one.
    /// </remarks>
    public static (string WorkFolder, bool IsDefault) EffectiveWorkFolder(ProcessingLibraryRecord library, string weirHome)
    {
        ArgumentNullException.ThrowIfNull(library);
        var raw = PyStrings.Strip(library.WorkFolder ?? string.Empty);
        if (raw.Length > 0)
        {
            return (raw, false);
        }

        return (DefaultWorkFolder(weirHome, PyStrings.Strip(library.MediaType ?? "movie").ToLowerInvariant()), true);
    }

    /// <summary>
    /// <c>resolve_processing_path_runtime_for_library</c>: one library's folders, or the sentence saying why they cannot be used.
    /// </summary>
    public static (ProcessingPathRuntime? Runtime, string? Problem) RuntimeForLibrary(ProcessingLibraryRecord library, string weirHome)
    {
        ArgumentNullException.ThrowIfNull(library);
        var label = PyStrings.Strip(library.Name).Length > 0 ? PyStrings.Strip(library.Name) : library.MediaType == "tv" ? "TV" : "Movies";
        var watchedRaw = PyStrings.Strip(library.WatchedFolder ?? string.Empty);
        if (watchedRaw.Length == 0)
        {
            return (null,
                $"The {label} library has no watched folder set. " +
                "Manual remux and folder-scan jobs need a watched folder to resolve relative paths. " +
                "Set it on Processing → Libraries before enqueueing or running those jobs.");
        }

        var watched = Resolve(watchedRaw);
        if (!Directory.Exists(watched))
        {
            return (null, $"The {label} library's watched folder must be an existing directory.");
        }

        var (workRaw, workIsDefault) = EffectiveWorkFolder(library, weirHome);
        var work = Resolve(workRaw);
        var outputRaw = PyStrings.Strip(library.OutputFolder ?? string.Empty);
        if (outputRaw.Length == 0)
        {
            return (null,
                $"The {label} library has no output folder set. " +
                "Set it on Processing → Libraries before running a live remux pass.");
        }

        var output = Resolve(outputRaw);
        if (!Directory.Exists(output))
        {
            return (null, $"The {label} library's output folder must be an existing directory.");
        }

        if (SameOrNested(work, output))
        {
            return (null, "The work/temp folder and output folder must be separate (no overlap or containment).");
        }

        if (SameOrNested(watched, output))
        {
            return (null, "The watched folder and output folder must be separate (no overlap or containment).");
        }

        if (SameOrNested(watched, work))
        {
            return (null, "The watched folder and work/temp folder must be separate (no overlap or containment).");
        }

        if (!workIsDefault && !Directory.Exists(work))
        {
            return (null, $"The {label} library's work/temp folder must be an existing directory when set to a custom path.");
        }

        return (new ProcessingPathRuntime
        {
            WatchedFolder = watched,
            OutputFolder = output,
            WorkFolderEffective = work,
            WorkFolderIsDefault = workIsDefault,
            SidecarPatternsCsv = library.SidecarPatternsCsv ?? string.Empty,
            PreserveOriginalTimestamps = library.PreserveOriginalTimestamps,
            OutputCollisionPolicy = string.IsNullOrEmpty(library.OutputCollisionPolicy) ? "replace" : library.OutputCollisionPolicy,
            HardwareDecodeMode = string.IsNullOrEmpty(library.HardwareDecodeMode) ? "off" : library.HardwareDecodeMode,
            HardwareDevice = library.HardwareDevice ?? string.Empty,
            HardwareDisabledVendorsCsv = library.HardwareDisabledVendorsCsv ?? string.Empty,
            FfmpegStrictness = string.IsNullOrEmpty(library.FfmpegStrictness) ? "normal" : library.FfmpegStrictness,
            RemuxWriter = Weir.Core.Media.RemuxWriterChoice.Normalize(library.RemuxWriter),
            RewriteWithFfmpeg = library.RewriteWithFfmpeg,
        }, null);
    }

    private static bool SameOrNested(string a, string b) => IsUnder(a, b) || IsUnder(b, a);

    /// <summary>
    /// <c>rules_config_for</c>: a library's rule set, including the original-language and metadata options the plain
    /// conversion (<see cref="RuleSetConversion.ToRulesConfig"/>, the fallback for a library without one) leaves out.
    /// </summary>
    public static ProcessingRulesConfig RulesConfigFor(ProcessingRuleSetRecord ruleSet)
    {
        ArgumentNullException.ThrowIfNull(ruleSet);
        return new ProcessingRulesConfig
        {
            PrimaryAudioLang = ruleSet.PrimaryAudioLang,
            SecondaryAudioLang = ruleSet.SecondaryAudioLang,
            TertiaryAudioLang = ruleSet.TertiaryAudioLang,
            DefaultAudioSlot = ruleSet.DefaultAudioSlot,
            RemoveCommentary = ruleSet.RemoveCommentary,
            // #545 item 4: rules_config_for used to pass the stored mode through unchanged while the fallback path
            // (RuleSetConversion.ToRulesConfig) normalized it; both paths now agree on the same normalization.
            SubtitleMode = RuleSetConversion.NormalizeSubtitleMode(ruleSet.SubtitleMode),
            SubtitleLangs = [.. (ruleSet.SubtitleLangsCsv ?? string.Empty).Split(',').Select(PyStrings.Strip).Where(x => x.Length > 0)],
            PreserveForcedSubs = ruleSet.PreserveForcedSubs,
            PreserveDefaultSubs = ruleSet.PreserveDefaultSubs,
            AudioPreferenceMode = RemuxRules.NormalizeAudioPreferenceMode(ruleSet.AudioPreferenceMode),
            AudioSortersJson = ruleSet.AudioSortersJson ?? string.Empty,
            RemoveHearingImpairedSubs = ruleSet.RemoveHearingImpairedSubs,
            AudioKeepMode = RemuxRules.NormalizeAudioKeepMode(ruleSet.AudioKeepMode),
            SubtitleMaxPerLanguage = ruleSet.SubtitleMaxPerLanguage,
            SubtitleQualityStrategy = RemuxRules.NormalizeSubtitleQualityStrategy(ruleSet.SubtitleQualityStrategy),
            OriginalLanguage = new OriginalLanguageRules
            {
                Enabled = ruleSet.KeepOriginalLanguage,
                AdditionalLanguages = OriginalLanguage.ParseAdditionalLanguages(ruleSet.OriginalLanguageAdditionalCsv),
                KeepOnlyFirst = ruleSet.OriginalLanguageKeepOnlyFirst,
                FirstIfNone = ruleSet.OriginalLanguageFirstIfNone,
                TreatEmptyAsOriginal = ruleSet.OriginalLanguageTreatEmptyAsOriginal,
            },
            Metadata = new MetadataRules
            {
                RemoveImages = ruleSet.RemoveImages,
                RemoveAttachments = ruleSet.RemoveAttachments,
                RemoveTitle = ruleSet.RemoveTitle,
                RemoveLanguageTags = ruleSet.RemoveLanguageTags,
                RemoveOtherMetadata = ruleSet.RemoveOtherMetadata,
                StandardizeTrackNames = ruleSet.StandardizeTrackNames,
                TrackNameTemplate = ruleSet.TrackNameTemplate,
                TrackNameOverrides = ruleSet.TrackNameOverrides,
                ClearVideoTrackNames = ruleSet.ClearVideoTrackNames,
                RemoveChapters = ruleSet.RemoveChapters,
            },
        };
    }

    /// <summary><c>cleanup_rejected_file</c>: delete one regular file under the watched folder, never a populated folder.</summary>
    public static RejectedFileCleanupResult CleanupRejectedFile(string watchedRoot, string filePath, string? action)
    {
        if (!string.Equals(PyStrings.Strip(action ?? "leave"), "delete_file", StringComparison.OrdinalIgnoreCase))
        {
            return new RejectedFileCleanupResult(false, "Weir left the rejected file in place because this library's cleanup action is Leave in place.");
        }

        string root;
        string source;
        try
        {
            root = Resolve(watchedRoot);
            source = Resolve(filePath);
            if (!Directory.Exists(root) && !File.Exists(root))
            {
                throw new FileNotFoundException($"[Errno 2] No such file or directory: '{watchedRoot}'");
            }

            if (!Directory.Exists(source) && !File.Exists(source))
            {
                throw new FileNotFoundException($"[Errno 2] No such file or directory: '{filePath}'");
            }

            if (RelativeTo(source, root) is null)
            {
                throw new ArgumentException($"'{source}' is not in the subpath of '{root}'");
            }
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or ArgumentException)
        {
            return new RejectedFileCleanupResult(false, $"Weir did not delete the rejected file because it was not safely inside the watched folder ({exception.Message}).");
        }

        if (SamePath(source, root) || !File.Exists(source))
        {
            return new RejectedFileCleanupResult(false, "Weir did not delete the rejected path because it is not a regular file inside the watched folder.");
        }

        try
        {
            File.Delete(source);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            return new RejectedFileCleanupResult(false, $"Weir could not delete the rejected file because it is locked or unavailable ({exception.Message}).");
        }

        var parent = Path.GetDirectoryName(source);
        while (parent is not null && !SamePath(parent, root))
        {
            try
            {
                Directory.Delete(parent, recursive: false);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                break;
            }

            parent = Path.GetDirectoryName(parent);
        }

        return new RejectedFileCleanupResult(true, "Weir deleted the rejected file because this library's cleanup action is Delete rejected file.");
    }
}
