using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Weir.Core.Auth;
using Weir.Core.Json;
using Weir.Core.Media;
using Weir.Core.Refiner;
using Weir.Core.Refiner.RemuxPass;
using Weir.Core.Rules;
using Weir.Core.Validation;
using Weir.Api.Http;
using Weir.Infrastructure.Browse;
using Weir.Infrastructure.Media;
using Weir.Infrastructure.Refiner;
using Weir.Infrastructure.Refiner.RemuxPass;

namespace Weir.Api.Endpoints;

/// <summary>
/// "Try on a file": preview what a library's saved or unsaved rules would do to a real media file,
/// without processing, queueing or writing anything (issue #502). Port has no Python original — there
/// is no preview endpoint in <c>refiner_libraries_api.py</c> today; this is new C#-only surface built
/// on the already-ported rules engine (<see cref="RemuxRules.PlanRemux"/>) and ffprobe layer
/// (<see cref="MediaTools"/>).
/// </summary>
public static class RefinerRulesPreviewEndpoints
{
    public static IEndpointRouteBuilder MapRefinerRulesPreviewEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapV1("POST", "/refiner/libraries/{library_id}/preview", PostPreviewAsync);
        return endpoints;
    }

    private static async Task<ApiResult> PostPreviewAsync(ApiRequest request)
    {
        var payload = await request.ReadBodyAsync().ConfigureAwait(false);
        var issues = new ValidationIssues();
        var pathIssues = new ValidationIssues();
        var libraryId = request.PathInt("library_id", pathIssues);
        var model = new BodyModel(payload, issues);
        var csrfToken = model.Str("csrf_token", minLength: 1);
        var relativePath = model.OptionalStr("relative_path", maxLength: 4000);
        var absolutePath = model.OptionalStr("absolute_path", maxLength: 4000);

        // "rules" is optional and, when present, validated exactly like a rule-set save (the same field
        // readers as PUT /refiner/rule-sets/{id}), just never written to the database. It is read by hand
        // rather than through BodyModel.Dict, which always requires the key.
        LibraryRules.RuleSetInput? ruleSetInput = null;
        if (payload is PyDict topLevel && topLevel.TryGetValue("rules", out var rawRules) && rawRules is not PyNull)
        {
            if (rawRules is not PyDict rulesDict)
            {
                issues.Add(new ValidationIssue("dict_type", ["body", "rules"], "Input should be a valid dictionary", rawRules));
            }
            else
            {
                var rulesModel = new BodyModel(rulesDict, issues);
                ruleSetInput = RefinerLibraryEndpoints.ReadRuleSetBody(rulesModel);
                rulesModel.Finish(ExtraFields.Forbid);
            }
        }

        // Ignore, not Forbid: "rules" is read by hand above (BodyModel.Dict always requires the key, and
        // this one is optional), so BodyModel never marks it declared and Forbid would misreport it as an
        // unknown field. The nested rules object is still validated strictly (see rulesModel.Finish above).
        model.Finish(ExtraFields.Ignore);
        pathIssues.ThrowIfAny();
        issues.ThrowIfAny();

        await request.RequireUserAsync(UserRoles.OperatorOrAdmin).ConfigureAwait(false);
        request.RequireConfirmationToken(csrfToken);

        var hasRelative = !string.IsNullOrWhiteSpace(relativePath);
        var hasAbsolute = !string.IsNullOrWhiteSpace(absolutePath);
        if (hasRelative == hasAbsolute)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "Give either relative_path or absolute_path, not both or neither.");
        }

        var uow = await request.DbAsync().ConfigureAwait(false);
        var library = await LibraryStore.GetAsync(uow, libraryId).ConfigureAwait(false)
            ?? throw new ApiException(StatusCodes.Status404NotFound, "That Refiner library does not exist.");

        var resolvedPath = hasRelative
            ? ResolveWithinLibraryFolders(library, relativePath!)
            : ResolveViaLocalBrowseAllowList(absolutePath!);

        var gate = request.Service<RulesPreviewGate>();
        if (!gate.TryEnter())
        {
            throw new ApiException(StatusCodes.Status409Conflict, "Another rules preview is already running. Try again in a moment.");
        }

        try
        {
            return await RunPreviewAsync(request, uow, library, resolvedPath, ruleSetInput).ConfigureAwait(false);
        }
        finally
        {
            gate.Release();
        }
    }

    /// <summary><c>relative_path</c> must resolve under the library's watched folder or its output
    /// folder, and the resulting file must exist. A library with neither folder configured, or a path
    /// that escapes both, is refused with a plain 400 detail (not a 422 field error — this is a
    /// business rule, not a shape check).</summary>
    private static string ResolveWithinLibraryFolders(RefinerLibraryRecord library, string relativePath)
    {
        foreach (var root in new[] { library.WatchedFolder, library.OutputFolder })
        {
            if (string.IsNullOrWhiteSpace(root))
            {
                continue;
            }

            string candidate;
            try
            {
                candidate = RemuxPassPaths.ResolveMediaFileUnderRoot(root, relativePath);
            }
            catch (ArgumentException)
            {
                continue;
            }

            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        throw new ApiException(
            StatusCodes.Status400BadRequest,
            "That path is not an existing file inside this library's watched or output folder.");
    }

    /// <summary><c>absolute_path</c> goes through the same allow-list the local file picker (<c>GET
    /// /system/directories</c>) already enforces: an absolute path under a real drive root (Windows) or
    /// the filesystem root, naming a file that exists.</summary>
    private static string ResolveViaLocalBrowseAllowList(string absolutePath)
    {
        try
        {
            return DirectoryBrowser.ValidateFilePath(absolutePath);
        }
        catch (DirectoryBrowseException exception)
        {
            throw new ApiException(exception.StatusCode, exception.Message);
        }
    }

    private static async Task<ApiResult> RunPreviewAsync(
        ApiRequest request,
        Weir.Infrastructure.Sqlite.UnitOfWork uow,
        RefinerLibraryRecord library,
        string resolvedPath,
        LibraryRules.RuleSetInput? ruleSetInput)
    {
        var scope = string.Equals(library.MediaType, RefinerMediaScopes.Tv, StringComparison.OrdinalIgnoreCase) ? RefinerMediaScopes.Tv : RefinerMediaScopes.Movie;

        var config = await BuildConfigAsync(uow, library, ruleSetInput).ConfigureAwait(false);

        var tools = request.Service<MediaTools>();
        System.Text.Json.JsonElement probeJson;
        try
        {
            probeJson = await tools.FfprobeJsonAsync(
                resolvedPath,
                probeSizeMb: request.Options.RefinerProbeSizeMb,
                analyzeDurationSeconds: request.Options.RefinerAnalyzeDurationSeconds,
                cancellationToken: request.Context.RequestAborted).ConfigureAwait(false);
        }
        catch (MediaUnreadableException exception)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, $"Weir could not read this file's contents: {exception.Message}");
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, $"ffprobe failed: {exception.Message}");
        }

        var probe = new ProbeResult(probeJson);
        var (video, audio, subtitles) = RemuxRules.SplitStreams(probe);
        if (video.Count == 0)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "This file contains no video stream, so Weir cannot preview a plan for it.");
        }

        PyDict? originalLanguageOut = null;
        if (config.OriginalLanguage is { Enabled: true } originalRules)
        {
            (config, originalLanguageOut) = await ApplyOriginalLanguageAsync(request, config, originalRules, scope, resolvedPath, audio).ConfigureAwait(false);
        }

        var plan = RemuxRules.PlanRemux(video, audio, subtitles, config, RemuxRules.AttachmentStreams(probe));
        if (plan is null)
        {
            throw new ApiException(StatusCodes.Status400BadRequest, "No audio track would remain with these rules, so Weir cannot preview a plan for this file.");
        }

        var remuxRequired = RemuxRules.IsRemuxRequired(plan, audio, subtitles);
        var duration = RemuxPassMedia.ProbeDurationSeconds(probe);
        var rows = RulesPreview.BuildTrackRows(probe, plan);
        var estimatedReduction = RulesPreview.EstimateDroppedBytes(probe, plan, duration);

        var result = new PyDict()
            .Set("library_id", library.Id)
            .Set("media_scope", scope)
            .Set("inspected_path", resolvedPath)
            .Set("tracks", new PyList(rows.Select(row => (PyJson)row.ToOut())))
            .Set("notes", new PyList(plan.AudioSelectionNotes.Select(n => (PyJson)new PyStr(n))))
            .Set("metadata_notes", new PyList(plan.MetadataNotes.Select(n => (PyJson)new PyStr(n))))
            .Set("remux_required", remuxRequired)
            .Set("estimated_size_reduction_bytes", estimatedReduction is { } bytes ? PyJson.Of(bytes) : PyJson.Null)
            .Set("estimated_size_reduction_is_estimate", true);
        if (originalLanguageOut is not null)
        {
            result.Set("original_language", originalLanguageOut);
        }

        return ApiRoutes.Ok(result);
    }

    /// <summary>Unsaved rules (validated exactly like a save) take priority; otherwise the library's saved
    /// rule set; otherwise the shipped defaults — the same fallback order a live pass uses.</summary>
    private static async Task<RefinerRulesConfig> BuildConfigAsync(Weir.Infrastructure.Sqlite.UnitOfWork uow, RefinerLibraryRecord library, LibraryRules.RuleSetInput? ruleSetInput)
    {
        if (ruleSetInput is not null)
        {
            RefinerRuleSetRecord previewRow;
            try
            {
                var label = (ruleSetInput.Name ?? string.Empty).Trim();
                previewRow = LibraryRules.ApplyRuleSetFields(new RefinerRuleSetRecord { Name = label.Length > 0 ? label : "Preview" }, ruleSetInput);
            }
            catch (RefinerLibraryException exception)
            {
                throw new ApiException(StatusCodes.Status400BadRequest, exception.Message);
            }

            return RemuxPassPaths.RulesConfigFor(previewRow);
        }

        if (library.RuleSetId is { } ruleSetId && await LibraryStore.GetRuleSetAsync(uow, ruleSetId).ConfigureAwait(false) is { } savedRow)
        {
            return RemuxPassPaths.RulesConfigFor(savedRow);
        }

        return RemuxRules.DefaultConfig();
    }

    /// <summary>
    /// #537 item 4's lookup, run the same way a live pass runs it: declining (no provider, no match,
    /// unreachable) leaves the configured language preferences in charge, with a note saying so, rather
    /// than failing the preview.
    /// </summary>
    private static async Task<(RefinerRulesConfig Config, PyDict Record)> ApplyOriginalLanguageAsync(
        ApiRequest request,
        RefinerRulesConfig config,
        OriginalLanguageRules rules,
        string scope,
        string resolvedPath,
        IReadOnlyList<ProbeStreamInfo> audio)
    {
        var lookupService = request.Service<IOriginalLanguageLookup>();
        LookupResult lookup;
        try
        {
            lookup = await lookupService.LookupAsync(scope, resolvedPath, origin: null, request.Context.RequestAborted).ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            lookup = new LookupResult { Status = LookupResult.StatusUnreachable, Detail = $"The metadata lookup failed ({exception.Message})." };
        }

        var tracks = audio
            .Where(stream => stream.Index is not null)
            .Select(stream => new OriginalLanguageTrack((int)stream.Index!.Value, stream.Tag("language") ?? string.Empty))
            .ToList();
        var outcome = OriginalLanguage.SelectTracks(rules, lookup, tracks);
        var record = new PyDict()
            .Set("lookup_status", lookup.Status)
            .Set("lookup_detail", lookup.Detail)
            .Set("original_language", lookup.Metadata?.OriginalLanguage)
            .Set("note", outcome.Note);
        return (config.WithOriginalLanguage(outcome), record);
    }
}
