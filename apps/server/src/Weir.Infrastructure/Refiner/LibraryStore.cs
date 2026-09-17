using Microsoft.Data.Sqlite;
using Weir.Core.Json;
using Weir.Core.Refiner;
using Weir.Core.Rules;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Refiner;

/// <summary>
/// SQLite access for Refiner libraries and rule sets (port of <c>refiner_library_service.py</c> and
/// <c>refiner_library_crud.py</c>'s persistence), plus the row IO <c>LibraryDiscoveryService</c> (#554,
/// port of <c>refiner_library_discovery.py</c>) needs for a discovered library's create and unlink. The
/// reject-support gate is not ported here: it lives in <c>RejectSupportEvaluator</c>.
/// </summary>
public static class LibraryStore
{
    private const string LibraryColumns =
        "id, name, enabled, media_type, display_order, watched_folder, work_folder, output_folder, " +
        "media_extensions_csv, exclude_markers_csv, include_patterns_csv, exclude_patterns_csv, min_file_size_mb, max_file_size_mb, " +
        "rejected_file_action, min_file_age_seconds, created_after, created_before, modified_after, modified_before, " +
        "exclude_hidden, top_level_only, sidecar_patterns_csv, preserve_original_timestamps, output_collision_policy, " +
        "hardware_decode_mode, hardware_device, hardware_disabled_vendors_csv, ffmpeg_strictness, scan_interval_seconds, " +
        "hold_minutes, file_detection_interval_seconds, ignore_size_changes, file_system_events_enabled, skip_access_tests, " +
        "schedule_enabled, schedule_hours_limited, schedule_days, schedule_grid, schedule_start, schedule_end, max_attempts, " +
        "retry_backoff_seconds, retry_execution_failures, retry_preflight_failures, failure_policy, max_concurrent_files, " +
        "priority, rule_set_id, discovered_from_connection_id, discovered_library_key, created_at, updated_at, " +
        // #548: appended, not inserted - ReadLibrary reads by position.
        "remux_writer, rewrite_with_ffmpeg";

    private const string RuleSetColumns =
        "id, name, primary_audio_lang, secondary_audio_lang, tertiary_audio_lang, default_audio_slot, remove_commentary, " +
        "subtitle_mode, subtitle_langs_csv, preserve_forced_subs, preserve_default_subs, audio_preference_mode, audio_sorters_json, " +
        "subtitle_sorters_json, keep_original_language, original_language_additional_csv, original_language_keep_only_first, " +
        "original_language_first_if_none, original_language_treat_empty_as_original, remove_images, remove_attachments, " +
        "remove_title, remove_language_tags, remove_other_metadata, remove_hearing_impaired_subs, audio_keep_mode, " +
        "subtitle_max_per_language, subtitle_quality_strategy, standardize_track_names, track_name_template, " +
        "track_name_override_forced, track_name_override_hearing_impaired, track_name_override_commentary, " +
        "track_name_override_audio_description, clear_video_track_names, remove_chapters, created_at, updated_at";

    public static async Task<List<RefinerLibraryRecord>> ListAsync(UnitOfWork uow, bool enabledOnly = false)
    {
        var sql = $"SELECT {LibraryColumns} FROM refiner_libraries" + (enabledOnly ? " WHERE enabled = 1" : string.Empty) +
                  " ORDER BY display_order, id";
        return await uow.QueryAsync(sql, ReadLibrary).ConfigureAwait(false);
    }

    public static Task<RefinerLibraryRecord?> GetAsync(UnitOfWork uow, long id) =>
        uow.QuerySingleAsync($"SELECT {LibraryColumns} FROM refiner_libraries WHERE id = @id", ReadLibrary, ("@id", id));

    public static Task<RefinerLibraryRecord?> GetByNameAsync(UnitOfWork uow, string name) =>
        uow.QuerySingleAsync($"SELECT {LibraryColumns} FROM refiner_libraries WHERE name = @name", ReadLibrary, ("@name", name));

    /// <summary><c>seeded_library_for_scope</c>: the oldest library covering a scope.</summary>
    public static Task<RefinerLibraryRecord?> SeededForScopeAsync(UnitOfWork uow, string mediaScope) =>
        uow.QuerySingleAsync(
            $"SELECT {LibraryColumns} FROM refiner_libraries WHERE media_type = @scope ORDER BY display_order, id LIMIT 1",
            ReadLibrary, ("@scope", RefinerMediaScopes.Normalize(mediaScope)));

    public static async Task<List<long>> ManagerConnectionIdsAsync(UnitOfWork uow, long libraryId)
    {
        var rows = await uow.QueryAsync(
            "SELECT connection_id FROM refiner_library_manager_links WHERE library_id = @id ORDER BY connection_id",
            reader => reader.GetInt64(0), ("@id", libraryId)).ConfigureAwait(false);
        return rows;
    }

    public static async Task<HashSet<long>> KnownConnectionIdsAsync(UnitOfWork uow, IReadOnlyList<long> ids)
    {
        if (ids.Count == 0)
        {
            return [];
        }

        var placeholders = string.Join(",", ids.Select((_, i) => $"@id{i}"));
        var parameters = ids.Select((id, i) => ($"@id{i}", (object?)id)).ToArray();
        var rows = await uow.QueryAsync(
            $"SELECT id FROM media_manager_connections WHERE id IN ({placeholders})",
            reader => reader.GetInt64(0), parameters).ConfigureAwait(false);
        return [.. rows];
    }

    /// <summary><c>active_job_count_for_library</c>: queued or leased Refiner jobs belonging to this library.</summary>
    public static async Task<int> ActiveJobCountAsync(UnitOfWork uow, RefinerLibraryRecord library)
    {
        var libraries = await ListAsync(uow).ConfigureAwait(false);
        var seededForScope = libraries.FirstOrDefault(row => row.MediaType == library.MediaType);
        var isSeeded = seededForScope is not null && seededForScope.Id == library.Id;

        var payloads = await uow.QueryAsync(
            "SELECT payload_json FROM refiner_jobs WHERE status IN ('pending', 'leased')",
            reader => reader.IsDBNull(0) ? null : reader.GetString(0)).ConfigureAwait(false);

        var count = 0;
        foreach (var raw in payloads)
        {
            if (string.IsNullOrWhiteSpace(raw))
            {
                continue;
            }

            PyJson data;
            try
            {
                data = PyJsonParser.Parse(raw);
            }
            catch (PyJsonDecodeException)
            {
                continue;
            }

            if (data is not PyDict dict)
            {
                continue;
            }

            if (dict.TryGetValue("library_id", out var libraryIdValue) && libraryIdValue is PyInt libraryIdInt)
            {
                if (libraryIdInt.Value == library.Id)
                {
                    count++;
                }

                continue;
            }

            if (isSeeded)
            {
                var scope = dict.TryGetValue("media_scope", out var scopeValue) && scopeValue is PyStr scopeStr
                    ? RefinerMediaScopes.Normalize(scopeStr.Value)
                    : RefinerMediaScopes.Movie;
                if (scope == library.MediaType)
                {
                    count++;
                }
            }
        }

        return count;
    }

    public static async Task<RefinerLibraryRecord> CreateAsync(UnitOfWork uow, RefinerLibraryInput body)
    {
        var existingNames = (await ListAsync(uow).ConfigureAwait(false)).Select(l => l.Name).ToHashSet(StringComparer.Ordinal);
        var name = LibraryRules.ValidateName(body.Name, existingNames);
        var scope = LibraryRules.ValidateScope(body.MediaType);
        var highestOrder = await uow.ScalarAsync("SELECT MAX(display_order) FROM refiner_libraries").ConfigureAwait(false);
        var displayOrder = (highestOrder is null or DBNull ? 0 : Convert.ToInt64(highestOrder, System.Globalization.CultureInfo.InvariantCulture)) + 1;

        var ruleSetExists = body.RuleSetId is { } wantedRuleSet && await GetRuleSetAsync(uow, wantedRuleSet).ConfigureAwait(false) is not null;
        var others = await OtherFoldersAsync(uow, excludeId: null).ConfigureAwait(false);
        var row = LibraryRules.ApplyFields(new RefinerLibraryRecord { Name = name, MediaType = scope, DisplayOrder = displayOrder }, body, ruleSetExists);
        LibraryRules.ValidateFolders(row.WatchedFolder, row.WorkFolder, row.OutputFolder, others);

        await InsertAsync(uow, row).ConfigureAwait(false);
        var created = await GetByNameAsync(uow, name).ConfigureAwait(false) ?? throw new InvalidOperationException("Library insert race.");
        await SetManagerLinksAsync(uow, created.Id, body.ManagerConnectionIds).ConfigureAwait(false);
        return created;
    }

    public static async Task<RefinerLibraryRecord> UpdateAsync(UnitOfWork uow, RefinerLibraryRecord existing, RefinerLibraryInput body)
    {
        var existingNames = (await ListAsync(uow).ConfigureAwait(false))
            .Where(l => l.Id != existing.Id).Select(l => l.Name).ToHashSet(StringComparer.Ordinal);
        var name = LibraryRules.ValidateName(body.Name, existingNames);
        var scope = LibraryRules.ValidateScope(body.MediaType);
        var ruleSetExists = body.RuleSetId is { } wantedRuleSet && await GetRuleSetAsync(uow, wantedRuleSet).ConfigureAwait(false) is not null;
        var others = await OtherFoldersAsync(uow, excludeId: existing.Id).ConfigureAwait(false);
        var row = LibraryRules.ApplyFields(existing with { Name = name, MediaType = scope }, body, ruleSetExists);
        LibraryRules.ValidateFolders(row.WatchedFolder, row.WorkFolder, row.OutputFolder, others);

        await UpdateRowAsync(uow, row).ConfigureAwait(false);
        var updated = await GetAsync(uow, existing.Id).ConfigureAwait(false) ?? throw new InvalidOperationException("Library disappeared during update.");
        await SetManagerLinksAsync(uow, updated.Id, body.ManagerConnectionIds).ConfigureAwait(false);
        return updated;
    }

    /// <summary>
    /// <c>import_libraries</c>'s row creation: a library made from a manager's own descriptor rather than an
    /// operator's request body, so <c>LibraryRules.ApplyFields</c>/<c>ValidateFolders</c> (folder-overlap and
    /// full-field validation) never runs — Python's version does not call <c>create_library</c> either, only
    /// <c>session.add</c>/<c>flush</c> on a row built from a handful of fields, every other column keeping its
    /// schema default (mirrored by <see cref="RefinerLibraryRecord"/>'s own property defaults).
    /// </summary>
    public static async Task<RefinerLibraryRecord> CreateDiscoveredAsync(UnitOfWork uow, RefinerLibraryRecord row)
    {
        await InsertAsync(uow, row).ConfigureAwait(false);
        return await GetByNameAsync(uow, row.Name).ConfigureAwait(false)
            ?? throw new InvalidOperationException("Discovered library insert race.");
    }

    /// <summary><c>unlink_library</c>: forget where a library came from, keeping the library itself untouched.</summary>
    public static async Task<RefinerLibraryRecord> UnlinkAsync(UnitOfWork uow, RefinerLibraryRecord row)
    {
        await uow.ExecuteAsync(
            "UPDATE refiner_libraries SET discovered_from_connection_id = NULL, discovered_library_key = NULL, " +
            "updated_at = CURRENT_TIMESTAMP WHERE id = @id",
            ("@id", row.Id)).ConfigureAwait(false);
        return await GetAsync(uow, row.Id).ConfigureAwait(false)
            ?? throw new InvalidOperationException("Library disappeared during unlink.");
    }

    public static async Task DeleteAsync(UnitOfWork uow, RefinerLibraryRecord row)
    {
        var active = await ActiveJobCountAsync(uow, row).ConfigureAwait(false);
        if (active > 0)
        {
            throw new RefinerLibraryException(
                $"{row.Name} still has {active} job{(active == 1 ? string.Empty : "s")} queued or running. " +
                "Wait for them to finish, or cancel them, before removing the library — they resolve their folders from it.");
        }

        await uow.ExecuteAsync("DELETE FROM refiner_libraries WHERE id = @id", ("@id", row.Id)).ConfigureAwait(false);
    }

    public static async Task<List<RefinerLibraryRecord>> ReorderAsync(UnitOfWork uow, IReadOnlyList<long> orderedIds)
    {
        var rows = (await ListAsync(uow).ConfigureAwait(false)).ToDictionary(r => r.Id);
        var unknown = orderedIds.Where(id => !rows.ContainsKey(id)).ToList();
        if (unknown.Count > 0)
        {
            throw new RefinerLibraryException($"No library with id {unknown[0]}.");
        }

        if (orderedIds.Distinct().Count() != rows.Count)
        {
            throw new RefinerLibraryException("Reordering must list every library exactly once.");
        }

        for (var position = 0; position < orderedIds.Count; position++)
        {
            await uow.ExecuteAsync(
                "UPDATE refiner_libraries SET display_order = @order WHERE id = @id",
                ("@order", (long)position), ("@id", orderedIds[position])).ConfigureAwait(false);
        }

        return await ListAsync(uow).ConfigureAwait(false);
    }

    public static async Task SetManagerLinksAsync(UnitOfWork uow, long libraryId, IReadOnlyList<long> connectionIds)
    {
        var known = await KnownConnectionIdsAsync(uow, connectionIds).ConfigureAwait(false);
        var wanted = LibraryRules.ValidateManagerConnections(connectionIds, known);
        var existing = (await ManagerConnectionIdsAsync(uow, libraryId).ConfigureAwait(false)).ToHashSet();
        foreach (var stale in existing.Except(wanted))
        {
            await uow.ExecuteAsync(
                "DELETE FROM refiner_library_manager_links WHERE library_id = @lib AND connection_id = @conn",
                ("@lib", libraryId), ("@conn", stale)).ConfigureAwait(false);
        }

        foreach (var added in wanted.Except(existing))
        {
            await uow.ExecuteAsync(
                "INSERT INTO refiner_library_manager_links (library_id, connection_id) VALUES (@lib, @conn)",
                ("@lib", libraryId), ("@conn", added)).ConfigureAwait(false);
        }
    }

    private static async Task<List<OtherLibraryFolders>> OtherFoldersAsync(UnitOfWork uow, long? excludeId)
    {
        var rows = await ListAsync(uow).ConfigureAwait(false);
        return [.. rows.Where(r => r.Id != excludeId).Select(r => new OtherLibraryFolders(r.Id, r.Name, r.WatchedFolder, r.OutputFolder))];
    }

    // ---- Rule sets --------------------------------------------------------------------------

    public static async Task<List<RefinerRuleSetRecord>> ListRuleSetsAsync(UnitOfWork uow) =>
        await uow.QueryAsync($"SELECT {RuleSetColumns} FROM refiner_rule_sets ORDER BY id", ReadRuleSet).ConfigureAwait(false);

    public static Task<RefinerRuleSetRecord?> GetRuleSetAsync(UnitOfWork uow, long id) =>
        uow.QuerySingleAsync($"SELECT {RuleSetColumns} FROM refiner_rule_sets WHERE id = @id", ReadRuleSet, ("@id", id));

    public static Task<RefinerRuleSetRecord?> GetRuleSetByNameAsync(UnitOfWork uow, string name) =>
        uow.QuerySingleAsync($"SELECT {RuleSetColumns} FROM refiner_rule_sets WHERE name = @name", ReadRuleSet, ("@name", name));

    public static async Task<int> RuleSetUsageCountAsync(UnitOfWork uow, long ruleSetId) =>
        (int)await uow.CountAsync("SELECT COUNT(*) FROM refiner_libraries WHERE rule_set_id = @id", ("@id", ruleSetId)).ConfigureAwait(false);

    public static async Task<RefinerRuleSetRecord> CreateRuleSetAsync(UnitOfWork uow, LibraryRules.RuleSetInput body)
    {
        var label = (body.Name ?? string.Empty).Trim();
        if (await GetRuleSetByNameAsync(uow, label).ConfigureAwait(false) is not null)
        {
            throw new RefinerLibraryException($"A rule set named '{label}' already exists.");
        }

        var row = LibraryRules.ApplyRuleSetFields(new RefinerRuleSetRecord { Name = label }, body);
        await InsertRuleSetAsync(uow, row).ConfigureAwait(false);
        return await GetRuleSetByNameAsync(uow, label).ConfigureAwait(false) ?? throw new InvalidOperationException("Rule set insert race.");
    }

    public static async Task<RefinerRuleSetRecord> UpdateRuleSetAsync(UnitOfWork uow, RefinerRuleSetRecord existing, LibraryRules.RuleSetInput body)
    {
        var label = (body.Name ?? string.Empty).Trim();
        var clash = await GetRuleSetByNameAsync(uow, label).ConfigureAwait(false);
        if (clash is not null && clash.Id != existing.Id)
        {
            throw new RefinerLibraryException($"A rule set named '{label}' already exists.");
        }

        var row = LibraryRules.ApplyRuleSetFields(existing with { Name = label }, body);
        await UpdateRuleSetRowAsync(uow, row).ConfigureAwait(false);
        return await GetRuleSetAsync(uow, existing.Id).ConfigureAwait(false) ?? throw new InvalidOperationException("Rule set disappeared during update.");
    }

    public static async Task DeleteRuleSetAsync(UnitOfWork uow, RefinerRuleSetRecord row)
    {
        var used = await RuleSetUsageCountAsync(uow, row.Id).ConfigureAwait(false);
        if (used > 0)
        {
            throw new RefinerLibraryException(
                $"{row.Name} is still used by {used} librar{(used == 1 ? "y" : "ies")}. " +
                "Point them at another rule set first — removing it would strip their audio and subtitle handling.");
        }

        await uow.ExecuteAsync("DELETE FROM refiner_rule_sets WHERE id = @id", ("@id", row.Id)).ConfigureAwait(false);
    }

    // ---- Row IO -------------------------------------------------------------------------------

    private static async Task InsertAsync(UnitOfWork uow, RefinerLibraryRecord row)
    {
        await uow.ExecuteAsync(
            "INSERT INTO refiner_libraries (name, enabled, media_type, display_order, watched_folder, work_folder, output_folder, " +
            "media_extensions_csv, exclude_markers_csv, include_patterns_csv, exclude_patterns_csv, min_file_size_mb, max_file_size_mb, " +
            "rejected_file_action, min_file_age_seconds, created_after, created_before, modified_after, modified_before, " +
            "exclude_hidden, top_level_only, sidecar_patterns_csv, preserve_original_timestamps, output_collision_policy, " +
            "hardware_decode_mode, hardware_device, hardware_disabled_vendors_csv, ffmpeg_strictness, scan_interval_seconds, " +
            "hold_minutes, file_detection_interval_seconds, ignore_size_changes, file_system_events_enabled, skip_access_tests, " +
            "schedule_enabled, schedule_hours_limited, schedule_days, schedule_grid, schedule_start, schedule_end, max_attempts, " +
            "retry_backoff_seconds, retry_execution_failures, retry_preflight_failures, failure_policy, max_concurrent_files, " +
            "priority, rule_set_id, discovered_from_connection_id, discovered_library_key, remux_writer, rewrite_with_ffmpeg) " +
            "VALUES (@name, @enabled, @media_type, " +
            "@display_order, @watched_folder, @work_folder, @output_folder, " +
            "@media_extensions_csv, @exclude_markers_csv, @include_patterns_csv, @exclude_patterns_csv, @min_file_size_mb, @max_file_size_mb, " +
            "@rejected_file_action, @min_file_age_seconds, @created_after, @created_before, @modified_after, @modified_before, " +
            "@exclude_hidden, @top_level_only, @sidecar_patterns_csv, @preserve_original_timestamps, @output_collision_policy, " +
            "@hardware_decode_mode, @hardware_device, @hardware_disabled_vendors_csv, @ffmpeg_strictness, @scan_interval_seconds, " +
            "@hold_minutes, @file_detection_interval_seconds, @ignore_size_changes, @file_system_events_enabled, @skip_access_tests, " +
            "@schedule_enabled, @schedule_hours_limited, @schedule_days, @schedule_grid, @schedule_start, @schedule_end, @max_attempts, " +
            "@retry_backoff_seconds, @retry_execution_failures, @retry_preflight_failures, @failure_policy, @max_concurrent_files, " +
            "@priority, @rule_set_id, @discovered_from_connection_id, @discovered_library_key, @remux_writer, @rewrite_with_ffmpeg)",
            LibraryParameters(row)).ConfigureAwait(false);
    }

    private static async Task UpdateRowAsync(UnitOfWork uow, RefinerLibraryRecord row)
    {
        await uow.ExecuteAsync(
            "UPDATE refiner_libraries SET name=@name, enabled=@enabled, media_type=@media_type, watched_folder=@watched_folder, " +
            "work_folder=@work_folder, output_folder=@output_folder, media_extensions_csv=@media_extensions_csv, " +
            "exclude_markers_csv=@exclude_markers_csv, include_patterns_csv=@include_patterns_csv, exclude_patterns_csv=@exclude_patterns_csv, " +
            "min_file_size_mb=@min_file_size_mb, max_file_size_mb=@max_file_size_mb, rejected_file_action=@rejected_file_action, " +
            "min_file_age_seconds=@min_file_age_seconds, created_after=@created_after, created_before=@created_before, " +
            "modified_after=@modified_after, modified_before=@modified_before, exclude_hidden=@exclude_hidden, top_level_only=@top_level_only, " +
            "sidecar_patterns_csv=@sidecar_patterns_csv, preserve_original_timestamps=@preserve_original_timestamps, " +
            "output_collision_policy=@output_collision_policy, hardware_decode_mode=@hardware_decode_mode, hardware_device=@hardware_device, " +
            "hardware_disabled_vendors_csv=@hardware_disabled_vendors_csv, ffmpeg_strictness=@ffmpeg_strictness, " +
            "scan_interval_seconds=@scan_interval_seconds, hold_minutes=@hold_minutes, file_detection_interval_seconds=@file_detection_interval_seconds, " +
            "ignore_size_changes=@ignore_size_changes, file_system_events_enabled=@file_system_events_enabled, skip_access_tests=@skip_access_tests, " +
            "schedule_enabled=@schedule_enabled, schedule_hours_limited=@schedule_hours_limited, schedule_days=@schedule_days, " +
            "schedule_grid=@schedule_grid, schedule_start=@schedule_start, schedule_end=@schedule_end, max_attempts=@max_attempts, " +
            "retry_backoff_seconds=@retry_backoff_seconds, retry_execution_failures=@retry_execution_failures, " +
            "retry_preflight_failures=@retry_preflight_failures, failure_policy=@failure_policy, max_concurrent_files=@max_concurrent_files, " +
            "priority=@priority, rule_set_id=@rule_set_id, remux_writer=@remux_writer, rewrite_with_ffmpeg=@rewrite_with_ffmpeg, " +
            "updated_at=CURRENT_TIMESTAMP WHERE id=@id",
            [.. LibraryParameters(row), ("@id", row.Id)]).ConfigureAwait(false);
    }

    private static (string, object?)[] LibraryParameters(RefinerLibraryRecord row) =>
    [
        ("@name", row.Name),
        ("@enabled", row.Enabled ? 1 : 0),
        ("@media_type", row.MediaType),
        ("@display_order", row.DisplayOrder),
        ("@watched_folder", row.WatchedFolder),
        ("@work_folder", row.WorkFolder),
        ("@output_folder", row.OutputFolder),
        ("@media_extensions_csv", row.MediaExtensionsCsv),
        ("@exclude_markers_csv", row.ExcludeMarkersCsv),
        ("@include_patterns_csv", row.IncludePatternsCsv),
        ("@exclude_patterns_csv", row.ExcludePatternsCsv),
        ("@min_file_size_mb", row.MinFileSizeMb),
        ("@max_file_size_mb", row.MaxFileSizeMb),
        ("@rejected_file_action", row.RejectedFileAction),
        ("@min_file_age_seconds", row.MinFileAgeSeconds),
        ("@created_after", SqliteValues.ToSqlite(row.CreatedAfter)),
        ("@created_before", SqliteValues.ToSqlite(row.CreatedBefore)),
        ("@modified_after", SqliteValues.ToSqlite(row.ModifiedAfter)),
        ("@modified_before", SqliteValues.ToSqlite(row.ModifiedBefore)),
        ("@exclude_hidden", row.ExcludeHidden ? 1 : 0),
        ("@top_level_only", row.TopLevelOnly ? 1 : 0),
        ("@sidecar_patterns_csv", row.SidecarPatternsCsv),
        ("@preserve_original_timestamps", row.PreserveOriginalTimestamps ? 1 : 0),
        ("@output_collision_policy", row.OutputCollisionPolicy),
        ("@hardware_decode_mode", row.HardwareDecodeMode),
        ("@hardware_device", row.HardwareDevice),
        ("@hardware_disabled_vendors_csv", row.HardwareDisabledVendorsCsv),
        ("@ffmpeg_strictness", row.FfmpegStrictness),
        ("@remux_writer", row.RemuxWriter),
        ("@rewrite_with_ffmpeg", row.RewriteWithFfmpeg ? 1 : 0),
        ("@scan_interval_seconds", row.ScanIntervalSeconds),
        ("@hold_minutes", row.HoldMinutes),
        ("@file_detection_interval_seconds", row.FileDetectionIntervalSeconds),
        ("@ignore_size_changes", row.IgnoreSizeChanges ? 1 : 0),
        ("@file_system_events_enabled", row.FileSystemEventsEnabled ? 1 : 0),
        ("@skip_access_tests", row.SkipAccessTests ? 1 : 0),
        ("@schedule_enabled", row.ScheduleEnabled ? 1 : 0),
        ("@schedule_hours_limited", row.ScheduleHoursLimited ? 1 : 0),
        ("@schedule_days", row.ScheduleDays),
        ("@schedule_grid", row.ScheduleGrid),
        ("@schedule_start", row.ScheduleStart),
        ("@schedule_end", row.ScheduleEnd),
        ("@max_attempts", row.MaxAttempts),
        ("@retry_backoff_seconds", row.RetryBackoffSeconds),
        ("@retry_execution_failures", row.RetryExecutionFailures ? 1 : 0),
        ("@retry_preflight_failures", row.RetryPreflightFailures ? 1 : 0),
        ("@failure_policy", row.FailurePolicy),
        ("@max_concurrent_files", row.MaxConcurrentFiles),
        ("@priority", row.Priority),
        ("@rule_set_id", row.RuleSetId),
        ("@discovered_from_connection_id", row.DiscoveredFromConnectionId),
        ("@discovered_library_key", row.DiscoveredLibraryKey),
    ];

    private static async Task InsertRuleSetAsync(UnitOfWork uow, RefinerRuleSetRecord row)
    {
        await uow.ExecuteAsync(
            "INSERT INTO refiner_rule_sets (name, primary_audio_lang, secondary_audio_lang, tertiary_audio_lang, default_audio_slot, " +
            "remove_commentary, subtitle_mode, subtitle_langs_csv, preserve_forced_subs, preserve_default_subs, audio_preference_mode, " +
            "audio_sorters_json, subtitle_sorters_json, keep_original_language, original_language_additional_csv, " +
            "original_language_keep_only_first, original_language_first_if_none, original_language_treat_empty_as_original, " +
            "remove_images, remove_attachments, remove_title, remove_language_tags, remove_other_metadata, " +
            "remove_hearing_impaired_subs, audio_keep_mode, subtitle_max_per_language, subtitle_quality_strategy, " +
            "standardize_track_names, track_name_template, track_name_override_forced, track_name_override_hearing_impaired, " +
            "track_name_override_commentary, track_name_override_audio_description, clear_video_track_names, remove_chapters) VALUES " +
            "(@name, @primary_audio_lang, @secondary_audio_lang, @tertiary_audio_lang, @default_audio_slot, @remove_commentary, " +
            "@subtitle_mode, @subtitle_langs_csv, @preserve_forced_subs, @preserve_default_subs, @audio_preference_mode, " +
            "@audio_sorters_json, @subtitle_sorters_json, @keep_original_language, @original_language_additional_csv, " +
            "@original_language_keep_only_first, @original_language_first_if_none, @original_language_treat_empty_as_original, " +
            "@remove_images, @remove_attachments, @remove_title, @remove_language_tags, @remove_other_metadata, " +
            "@remove_hearing_impaired_subs, @audio_keep_mode, @subtitle_max_per_language, @subtitle_quality_strategy, " +
            "@standardize_track_names, @track_name_template, @track_name_override_forced, @track_name_override_hearing_impaired, " +
            "@track_name_override_commentary, @track_name_override_audio_description, @clear_video_track_names, @remove_chapters)",
            RuleSetParameters(row)).ConfigureAwait(false);
    }

    private static async Task UpdateRuleSetRowAsync(UnitOfWork uow, RefinerRuleSetRecord row)
    {
        await uow.ExecuteAsync(
            "UPDATE refiner_rule_sets SET name=@name, primary_audio_lang=@primary_audio_lang, secondary_audio_lang=@secondary_audio_lang, " +
            "tertiary_audio_lang=@tertiary_audio_lang, default_audio_slot=@default_audio_slot, remove_commentary=@remove_commentary, " +
            "subtitle_mode=@subtitle_mode, subtitle_langs_csv=@subtitle_langs_csv, preserve_forced_subs=@preserve_forced_subs, " +
            "preserve_default_subs=@preserve_default_subs, audio_preference_mode=@audio_preference_mode, audio_sorters_json=@audio_sorters_json, " +
            "subtitle_sorters_json=@subtitle_sorters_json, keep_original_language=@keep_original_language, " +
            "original_language_additional_csv=@original_language_additional_csv, original_language_keep_only_first=@original_language_keep_only_first, " +
            "original_language_first_if_none=@original_language_first_if_none, " +
            "original_language_treat_empty_as_original=@original_language_treat_empty_as_original, remove_images=@remove_images, " +
            "remove_attachments=@remove_attachments, remove_title=@remove_title, remove_language_tags=@remove_language_tags, " +
            "remove_other_metadata=@remove_other_metadata, remove_hearing_impaired_subs=@remove_hearing_impaired_subs, " +
            "audio_keep_mode=@audio_keep_mode, subtitle_max_per_language=@subtitle_max_per_language, " +
            "subtitle_quality_strategy=@subtitle_quality_strategy, standardize_track_names=@standardize_track_names, " +
            "track_name_template=@track_name_template, track_name_override_forced=@track_name_override_forced, " +
            "track_name_override_hearing_impaired=@track_name_override_hearing_impaired, " +
            "track_name_override_commentary=@track_name_override_commentary, " +
            "track_name_override_audio_description=@track_name_override_audio_description, " +
            "clear_video_track_names=@clear_video_track_names, remove_chapters=@remove_chapters, " +
            "updated_at=CURRENT_TIMESTAMP WHERE id=@id",
            [.. RuleSetParameters(row), ("@id", row.Id)]).ConfigureAwait(false);
    }

    private static (string, object?)[] RuleSetParameters(RefinerRuleSetRecord row) =>
    [
        ("@name", row.Name),
        ("@primary_audio_lang", row.PrimaryAudioLang),
        ("@secondary_audio_lang", row.SecondaryAudioLang),
        ("@tertiary_audio_lang", row.TertiaryAudioLang),
        ("@default_audio_slot", row.DefaultAudioSlot),
        ("@remove_commentary", row.RemoveCommentary ? 1 : 0),
        ("@subtitle_mode", row.SubtitleMode),
        ("@subtitle_langs_csv", row.SubtitleLangsCsv),
        ("@preserve_forced_subs", row.PreserveForcedSubs ? 1 : 0),
        ("@preserve_default_subs", row.PreserveDefaultSubs ? 1 : 0),
        ("@audio_preference_mode", row.AudioPreferenceMode),
        ("@audio_sorters_json", row.AudioSortersJson),
        ("@subtitle_sorters_json", row.SubtitleSortersJson),
        ("@keep_original_language", row.KeepOriginalLanguage ? 1 : 0),
        ("@original_language_additional_csv", row.OriginalLanguageAdditionalCsv),
        ("@original_language_keep_only_first", row.OriginalLanguageKeepOnlyFirst ? 1 : 0),
        ("@original_language_first_if_none", row.OriginalLanguageFirstIfNone ? 1 : 0),
        ("@original_language_treat_empty_as_original", row.OriginalLanguageTreatEmptyAsOriginal ? 1 : 0),
        ("@remove_images", row.RemoveImages ? 1 : 0),
        ("@remove_attachments", row.RemoveAttachments ? 1 : 0),
        ("@remove_title", row.RemoveTitle ? 1 : 0),
        ("@remove_language_tags", row.RemoveLanguageTags ? 1 : 0),
        ("@remove_other_metadata", row.RemoveOtherMetadata ? 1 : 0),
        ("@remove_hearing_impaired_subs", row.RemoveHearingImpairedSubs ? 1 : 0),
        ("@audio_keep_mode", row.AudioKeepMode),
        ("@subtitle_max_per_language", row.SubtitleMaxPerLanguage),
        ("@subtitle_quality_strategy", row.SubtitleQualityStrategy),
        ("@standardize_track_names", row.StandardizeTrackNames ? 1 : 0),
        ("@track_name_template", row.TrackNameTemplate),
        ("@track_name_override_forced", row.TrackNameOverrides.Forced),
        ("@track_name_override_hearing_impaired", row.TrackNameOverrides.HearingImpaired),
        ("@track_name_override_commentary", row.TrackNameOverrides.Commentary),
        ("@track_name_override_audio_description", row.TrackNameOverrides.AudioDescription),
        ("@clear_video_track_names", row.ClearVideoTrackNames ? 1 : 0),
        ("@remove_chapters", row.RemoveChapters ? 1 : 0),
    ];

    private static RefinerLibraryRecord ReadLibrary(SqliteDataReader reader) => new()
    {
        Id = reader.GetInt64(0),
        Name = SqliteValues.GetString(reader, 1),
        Enabled = SqliteValues.GetBool(reader, 2),
        MediaType = SqliteValues.GetString(reader, 3),
        DisplayOrder = SqliteValues.GetInt64(reader, 4),
        WatchedFolder = SqliteValues.GetString(reader, 5),
        WorkFolder = SqliteValues.GetString(reader, 6),
        OutputFolder = SqliteValues.GetString(reader, 7),
        MediaExtensionsCsv = SqliteValues.GetString(reader, 8),
        ExcludeMarkersCsv = SqliteValues.GetString(reader, 9),
        IncludePatternsCsv = SqliteValues.GetString(reader, 10),
        ExcludePatternsCsv = SqliteValues.GetString(reader, 11),
        MinFileSizeMb = SqliteValues.GetInt64(reader, 12),
        MaxFileSizeMb = SqliteValues.GetInt64(reader, 13),
        RejectedFileAction = SqliteValues.GetString(reader, 14),
        MinFileAgeSeconds = SqliteValues.GetInt64(reader, 15),
        CreatedAfter = SqliteValues.GetDateTimeOrNull(reader, 16),
        CreatedBefore = SqliteValues.GetDateTimeOrNull(reader, 17),
        ModifiedAfter = SqliteValues.GetDateTimeOrNull(reader, 18),
        ModifiedBefore = SqliteValues.GetDateTimeOrNull(reader, 19),
        ExcludeHidden = SqliteValues.GetBool(reader, 20),
        TopLevelOnly = SqliteValues.GetBool(reader, 21),
        SidecarPatternsCsv = SqliteValues.GetString(reader, 22),
        PreserveOriginalTimestamps = SqliteValues.GetBool(reader, 23),
        OutputCollisionPolicy = SqliteValues.GetString(reader, 24),
        HardwareDecodeMode = SqliteValues.GetString(reader, 25),
        HardwareDevice = SqliteValues.GetString(reader, 26),
        HardwareDisabledVendorsCsv = SqliteValues.GetString(reader, 27),
        FfmpegStrictness = SqliteValues.GetString(reader, 28),
        ScanIntervalSeconds = SqliteValues.GetInt64(reader, 29),
        HoldMinutes = SqliteValues.GetInt64(reader, 30),
        FileDetectionIntervalSeconds = SqliteValues.GetInt64(reader, 31),
        IgnoreSizeChanges = SqliteValues.GetBool(reader, 32),
        FileSystemEventsEnabled = SqliteValues.GetBool(reader, 33),
        SkipAccessTests = SqliteValues.GetBool(reader, 34),
        ScheduleEnabled = SqliteValues.GetBool(reader, 35),
        ScheduleHoursLimited = SqliteValues.GetBool(reader, 36),
        ScheduleDays = SqliteValues.GetString(reader, 37),
        ScheduleGrid = SqliteValues.GetString(reader, 38),
        ScheduleStart = SqliteValues.GetString(reader, 39),
        ScheduleEnd = SqliteValues.GetString(reader, 40),
        MaxAttempts = SqliteValues.GetInt64(reader, 41),
        RetryBackoffSeconds = SqliteValues.GetInt64(reader, 42),
        RetryExecutionFailures = SqliteValues.GetBool(reader, 43),
        RetryPreflightFailures = SqliteValues.GetBool(reader, 44),
        FailurePolicy = SqliteValues.GetString(reader, 45),
        MaxConcurrentFiles = SqliteValues.GetInt64(reader, 46),
        Priority = SqliteValues.GetInt64(reader, 47),
        RuleSetId = reader.IsDBNull(48) ? null : reader.GetInt64(48),
        DiscoveredFromConnectionId = reader.IsDBNull(49) ? null : reader.GetInt64(49),
        DiscoveredLibraryKey = SqliteValues.GetStringOrNull(reader, 50),
        CreatedAt = SqliteValues.GetDateTime(reader, 51),
        UpdatedAt = SqliteValues.GetDateTime(reader, 52),
        RemuxWriter = SqliteValues.GetString(reader, 53),
        RewriteWithFfmpeg = SqliteValues.GetBool(reader, 54),
    };

    private static RefinerRuleSetRecord ReadRuleSet(SqliteDataReader reader) => new()
    {
        Id = reader.GetInt64(0),
        Name = SqliteValues.GetString(reader, 1),
        PrimaryAudioLang = SqliteValues.GetString(reader, 2),
        SecondaryAudioLang = SqliteValues.GetString(reader, 3),
        TertiaryAudioLang = SqliteValues.GetString(reader, 4),
        DefaultAudioSlot = SqliteValues.GetString(reader, 5),
        RemoveCommentary = SqliteValues.GetBool(reader, 6),
        SubtitleMode = SqliteValues.GetString(reader, 7),
        SubtitleLangsCsv = SqliteValues.GetString(reader, 8),
        PreserveForcedSubs = SqliteValues.GetBool(reader, 9),
        PreserveDefaultSubs = SqliteValues.GetBool(reader, 10),
        AudioPreferenceMode = SqliteValues.GetString(reader, 11),
        AudioSortersJson = SqliteValues.GetString(reader, 12),
        SubtitleSortersJson = SqliteValues.GetString(reader, 13),
        KeepOriginalLanguage = SqliteValues.GetBool(reader, 14),
        OriginalLanguageAdditionalCsv = SqliteValues.GetString(reader, 15),
        OriginalLanguageKeepOnlyFirst = SqliteValues.GetBool(reader, 16),
        OriginalLanguageFirstIfNone = SqliteValues.GetBool(reader, 17),
        OriginalLanguageTreatEmptyAsOriginal = SqliteValues.GetBool(reader, 18),
        RemoveImages = SqliteValues.GetBool(reader, 19),
        RemoveAttachments = SqliteValues.GetBool(reader, 20),
        RemoveTitle = SqliteValues.GetBool(reader, 21),
        RemoveLanguageTags = SqliteValues.GetBool(reader, 22),
        RemoveOtherMetadata = SqliteValues.GetBool(reader, 23),
        RemoveHearingImpairedSubs = SqliteValues.GetBool(reader, 24),
        AudioKeepMode = SqliteValues.GetString(reader, 25),
        SubtitleMaxPerLanguage = (int)SqliteValues.GetInt64(reader, 26),
        SubtitleQualityStrategy = SqliteValues.GetString(reader, 27),
        StandardizeTrackNames = SqliteValues.GetBool(reader, 28),
        TrackNameTemplate = SqliteValues.GetString(reader, 29),
        TrackNameOverrides = new TrackNameOverrides
        {
            Forced = SqliteValues.GetString(reader, 30),
            HearingImpaired = SqliteValues.GetString(reader, 31),
            Commentary = SqliteValues.GetString(reader, 32),
            AudioDescription = SqliteValues.GetString(reader, 33),
        },
        ClearVideoTrackNames = SqliteValues.GetBool(reader, 34),
        RemoveChapters = SqliteValues.GetBool(reader, 35),
        CreatedAt = SqliteValues.GetDateTime(reader, 36),
        UpdatedAt = SqliteValues.GetDateTime(reader, 37),
    };
}
