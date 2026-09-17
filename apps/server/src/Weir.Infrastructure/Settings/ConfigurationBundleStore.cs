using System.Globalization;
using Microsoft.Data.Sqlite;
using Weir.Core.Json;
using Weir.Core.Settings;
using Weir.Core.Time;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Settings;

/// <summary>
/// Export and restore of the settings rows (port of <c>weir.platform.configuration_bundle.service</c>),
/// format version 4, still reading version 3.
/// </summary>
public static class ConfigurationBundleStore
{
    public const int FormatVersion = 4;

    private const string SuiteTable = "suite_settings";
    private const string ArrTable = "arr_library_operator_settings";
    private const string RefinerOperatorTable = "refiner_operator_settings";
    private const string RuleSetsTable = "refiner_rule_sets";
    private const string LibrariesTable = "refiner_libraries";

    private enum ColumnKind
    {
        Raw,
        Boolean,
        DateTime,
    }

    private sealed record Column(string Name, ColumnKind Kind);

    /// <summary><c>build_configuration_bundle</c>. Throws <see cref="PyValueErrorException"/> when a required row is missing.</summary>
    public static async Task<PyDict> BuildAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        var suite = await ReadRowsAsync(uow, SuiteTable, "WHERE id = 1").ConfigureAwait(false);
        var arr = await ReadRowsAsync(uow, ArrTable, "WHERE id = 1").ConfigureAwait(false);
        var refinerOperator = await ReadRowsAsync(uow, RefinerOperatorTable, "WHERE id = 1").ConfigureAwait(false);
        var libraries = await ReadRowsAsync(uow, LibrariesTable, "ORDER BY id").ConfigureAwait(false);
        var ruleSets = await ReadRowsAsync(uow, RuleSetsTable, "ORDER BY id").ConfigureAwait(false);
        if (arr.Count == 0)
        {
            throw new PyValueErrorException("Missing required configuration row: arr_library_operator_settings");
        }

        if (refinerOperator.Count == 0)
        {
            throw new PyValueErrorException("Missing required configuration row: refiner_operator_settings");
        }

        return new PyDict()
            .Set("format_version", FormatVersion)
            .Set("suite_settings", suite[0])
            .Set("arr_library_operator_settings", arr[0])
            .Set("refiner_operator_settings", refinerOperator[0])
            .Set("refiner_rule_sets", new PyList(ruleSets))
            .Set("refiner_libraries", new PyList(libraries));
    }

    /// <summary>
    /// <c>apply_configuration_bundle</c>. <see cref="PyValueErrorException"/> becomes a 400; anything else
    /// (<see cref="PyTypeErrorException"/>, <see cref="SqliteException"/>) is a server error, as in Python.
    /// </summary>
    public static async Task ApplyAsync(UnitOfWork uow, PyDict bundle, ITimeZoneResolver zones)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(bundle);
        var supported = bundle.Get("format_version") switch
        {
            PyInt i => i.Value == 3 || i.Value == 4,
            PyFloat f => f.Value is 3.0 or 4.0,
            _ => false,
        };
        if (!supported)
        {
            throw new PyValueErrorException("Unsupported configuration bundle format_version (this build reads 3, 4).");
        }

        foreach (var key in new[] { SuiteTable, ArrTable, RefinerOperatorTable })
        {
            if (!bundle.ContainsKey(key))
            {
                throw new PyValueErrorException($"Bundle is missing required section: {key}");
            }
        }

        await ApplySuiteSettingsAsync(uow, bundle[SuiteTable], zones).ConfigureAwait(false);
        await ApplySingletonAsync(uow, ArrTable, bundle[ArrTable]).ConfigureAwait(false);
        await ApplySingletonAsync(uow, RefinerOperatorTable, bundle[RefinerOperatorTable]).ConfigureAwait(false);
        await RestoreRefinerLibrariesAsync(uow, bundle).ConfigureAwait(false);
    }

    private static async Task ApplySuiteSettingsAsync(UnitOfWork uow, PyJson section, ITimeZoneResolver zones)
    {
        var ss = section as PyDict ?? throw new PyTypeErrorException($"'{section.PythonTypeName}' object is not subscriptable");
        var name = PyConvert.Str(Required(ss, "product_display_name"));
        var noticeValue = ss.Get("signed_in_home_notice");
        var timezone = PyConvert.Str(Required(ss, "app_timezone"));
        var logRetention = PyConvert.ToInt(Required(ss, "log_retention_days"));
        string? notice = null;
        if (noticeValue is not null && noticeValue.IsTruthy)
        {
            notice = noticeValue is PyStr s ? s.Value : throw new PyTypeErrorException($"'{noticeValue.PythonTypeName}' object has no attribute 'strip'");
        }

        bool? backupEnabled = ss.Get("configuration_backup_enabled") is { } enabledValue and not PyNull ? enabledValue.IsTruthy : null;
        long? backupHours = null;
        var hoursValue = ss.Get("configuration_backup_interval_hours");

        // Same order as apply_suite_settings_put: name, notice, timezone, log retention, then activity and interval.
        var normalized = SuiteSettingsRules.Normalize(new SuiteSettingsUpdate(name, notice, timezone, Saturate(logRetention)), zones);
        long? activity = null;
        if (ss.Get("activity_retention_days") is { } activityValue and not PyNull)
        {
            activity = Saturate(PyConvert.ToInt(activityValue));
            if (activity is < 0 or > 3650)
            {
                throw new PyValueErrorException("Activity history must be kept between 0 (forever) and 3650 days.");
            }
        }

        normalized = normalized with { ActivityRetentionDays = activity };
        if (hoursValue is not null and not PyNull)
        {
            backupHours = Saturate(PyConvert.ToInt(hoursValue));
            if (backupHours is < 1 or > 720)
            {
                throw new PyValueErrorException("Backup interval must be between 1 and 720 hours.");
            }
        }

        normalized = normalized with { ConfigurationBackupEnabled = backupEnabled, ConfigurationBackupIntervalHours = backupHours };
        var before = await SuiteSettingsStore.EnsureAsync(uow).ConfigureAwait(false);
        await SuiteSettingsStore.UpdateAsync(uow, before, SuiteSettingsRules.Apply(before, normalized)).ConfigureAwait(false);
    }

    private static async Task ApplySingletonAsync(UnitOfWork uow, string table, PyJson section)
    {
        var data = section as PyDict ?? throw new PyTypeErrorException($"'{section.PythonTypeName}' object has no attribute 'items'");
        var columns = await ColumnsAsync(uow, table).ConfigureAwait(false);
        var kwargs = ToKwargs(columns, data);
        var pk = kwargs.GetValueOrDefault("id");
        var loaded = pk is null or PyNull ? null : await ReadTypedRowAsync(uow, table, columns, pk).ConfigureAwait(false);
        if (loaded is null)
        {
            await InsertAsync(uow, table, columns, kwargs).ConfigureAwait(false);
        }
        else
        {
            var sets = new List<string>();
            var parameters = new List<(string, object?)>();
            foreach (var (key, value) in kwargs)
            {
                var column = columns[key];
                if (!PythonEquals(column.Kind, loaded[key], value))
                {
                    sets.Add($"\"{key}\"=${key}");
                    parameters.Add(($"${key}", Bind(column, value)));
                }
            }

            if (sets.Count > 0)
            {
                if (columns.ContainsKey("updated_at") && !parameters.Any(p => p.Item1 == "$updated_at"))
                {
                    sets.Add("updated_at=CURRENT_TIMESTAMP");
                }

                parameters.Add(("$__pk", loaded["id"] is PyJson id ? PyConvert.ToDatabase(id) : DBNull.Value));
                await uow.ExecuteAsync($"UPDATE {table} SET {string.Join(", ", sets)} WHERE id = $__pk", [.. parameters]).ConfigureAwait(false);
            }
        }
    }

    private static async Task RestoreRefinerLibrariesAsync(UnitOfWork uow, PyDict bundle)
    {
        if (bundle.ContainsKey(LibrariesTable))
        {
            await uow.ExecuteAsync("DELETE FROM refiner_libraries").ConfigureAwait(false);
            await uow.ExecuteAsync("DELETE FROM refiner_rule_sets").ConfigureAwait(false);
            var ruleColumns = await ColumnsAsync(uow, RuleSetsTable).ConfigureAwait(false);
            var libraryColumns = await ColumnsAsync(uow, LibrariesTable).ConfigureAwait(false);
            foreach (var row in Iterate(bundle.Get(RuleSetsTable) ?? new PyList()))
            {
                var data = row as PyDict ?? throw new PyTypeErrorException($"'{row.PythonTypeName}' object has no attribute 'items'");
                await InsertAsync(uow, RuleSetsTable, ruleColumns, ToKwargs(ruleColumns, data)).ConfigureAwait(false);
            }

            foreach (var row in Iterate(bundle[LibrariesTable]))
            {
                var data = row as PyDict ?? throw new PyTypeErrorException($"'{row.PythonTypeName}' object has no attribute 'items'");
                if (!data.ContainsKey("media_type") && data.ContainsKey("media_scope"))
                {
                    data = data.Copy().Set("media_type", data["media_scope"]);
                }

                await InsertAsync(uow, LibrariesTable, libraryColumns, ToKwargs(libraryColumns, data)).ConfigureAwait(false);
            }

            return;
        }

        var legacyPaths = LegacySection(bundle, "refiner_path_settings");
        var legacyRules = LegacySection(bundle, "refiner_remux_rules_settings");
        if (legacyPaths.Count == 0 && legacyRules.Count == 0)
        {
            return;
        }

        foreach (var (scope, prefix) in new[] { ("movie", string.Empty), ("tv", "tv_") })
        {
            var library = await uow.QuerySingleAsync(
                "SELECT id, watched_folder, work_folder, output_folder, scan_interval_seconds, rule_set_id FROM refiner_libraries " +
                "WHERE media_type = $scope ORDER BY display_order, id LIMIT 1 OFFSET 0",
                reader => new
                {
                    Id = SqliteValues.GetInt64(reader, 0),
                    Watched = SqliteValues.GetString(reader, 1),
                    Work = SqliteValues.GetString(reader, 2),
                    Output = SqliteValues.GetString(reader, 3),
                    Interval = SqliteValues.GetInt64(reader, 4),
                    RuleSetId = reader.IsDBNull(5) ? (long?)null : SqliteValues.GetInt64(reader, 5),
                },
                ("$scope", scope)).ConfigureAwait(false);
            if (library is null)
            {
                continue;
            }

            var librarySets = new List<string>();
            var libraryParameters = new List<(string, object?)> { ("$id", library.Id) };
            void SetText(string column, PyJson? value, string current)
            {
                if (value is null or PyNull)
                {
                    return;
                }

                var text = value.IsTruthy ? PyConvert.Str(value) : string.Empty;
                if (text != current)
                {
                    librarySets.Add($"{column}=${column}");
                    libraryParameters.Add(($"${column}", text));
                }
            }

            SetText("watched_folder", legacyPaths.Get($"refiner_{prefix}watched_folder"), library.Watched);
            SetText("work_folder", legacyPaths.Get($"refiner_{prefix}work_folder"), library.Work);
            SetText("output_folder", legacyPaths.Get($"refiner_{prefix}output_folder"), library.Output);
            if (legacyPaths.Get($"{(scope == "tv" ? "tv" : "movie")}_watched_folder_check_interval_seconds") is { } interval and not PyNull)
            {
                var seconds = Saturate(PyConvert.ToInt(interval));
                if (seconds != library.Interval)
                {
                    librarySets.Add("scan_interval_seconds=$scan_interval_seconds");
                    libraryParameters.Add(("$scan_interval_seconds", seconds));
                }
            }

            if (librarySets.Count > 0)
            {
                librarySets.Add("updated_at=CURRENT_TIMESTAMP");
                await uow.ExecuteAsync($"UPDATE refiner_libraries SET {string.Join(", ", librarySets)} WHERE id = $id", [.. libraryParameters]).ConfigureAwait(false);
            }

            if (library.RuleSetId is not { } ruleSetId || ruleSetId == 0 || legacyRules.Count == 0)
            {
                continue;
            }

            var ruleColumns = await ColumnsAsync(uow, RuleSetsTable).ConfigureAwait(false);
            var ruleSet = await ReadTypedRowAsync(uow, RuleSetsTable, ruleColumns, new PyInt(ruleSetId)).ConfigureAwait(false);
            if (ruleSet is null)
            {
                continue;
            }

            var sets = new List<string>();
            var parameters = new List<(string, object?)> { ("$id", ruleSetId) };
            foreach (var field in new[] { "primary_audio_lang", "secondary_audio_lang", "tertiary_audio_lang", "default_audio_slot", "subtitle_mode", "subtitle_langs_csv", "audio_preference_mode" })
            {
                if (legacyRules.Get(prefix + field) is { } value and not PyNull)
                {
                    var text = PyConvert.Str(value);
                    if (!PythonEquals(ColumnKind.Raw, ruleSet[field], new PyStr(text)))
                    {
                        sets.Add($"{field}=${field}");
                        parameters.Add(($"${field}", text));
                    }
                }
            }

            foreach (var field in new[] { "remove_commentary", "preserve_forced_subs", "preserve_default_subs" })
            {
                if (legacyRules.Get(prefix + field) is { } value and not PyNull)
                {
                    var flag = value.IsTruthy;
                    if (!PythonEquals(ColumnKind.Boolean, ruleSet[field], PyJson.Of(flag)))
                    {
                        sets.Add($"{field}=${field}");
                        parameters.Add(($"${field}", flag ? 1 : 0));
                    }
                }
            }

            if (sets.Count > 0)
            {
                sets.Add("updated_at=CURRENT_TIMESTAMP");
                await uow.ExecuteAsync($"UPDATE refiner_rule_sets SET {string.Join(", ", sets)} WHERE id = $id", [.. parameters]).ConfigureAwait(false);
            }
        }
    }

    private static PyDict LegacySection(PyDict bundle, string key)
    {
        var value = bundle.Get(key);
        if (value is null || !value.IsTruthy)
        {
            return new PyDict();
        }

        return value as PyDict ?? throw new PyTypeErrorException($"'{value.PythonTypeName}' object has no attribute 'get'");
    }

    private static IEnumerable<PyJson> Iterate(PyJson value) => value switch
    {
        PyList list => list.Items,
        PyDict dict => dict.Keys.Select(key => (PyJson)new PyStr(key)),
        PyStr text => text.Value.Select(c => (PyJson)new PyStr(c.ToString())),
        _ => throw new PyTypeErrorException($"'{value.PythonTypeName}' object is not iterable"),
    };

    private static PyJson Required(PyDict dict, string key) =>
        dict.Get(key) ?? throw new PyTypeErrorException($"KeyError: {PyConvert.ReprString(key)}");

    private static long Saturate(System.Numerics.BigInteger value) =>
        value > long.MaxValue ? long.MaxValue : value < long.MinValue ? long.MinValue : (long)value;

    /// <summary><c>dict_to_model_kwargs</c>: column keys only, timestamps parsed with <c>fromisoformat</c>.</summary>
    private static List<KeyValuePair<string, PyJson>> ToKwargsList(Dictionary<string, Column> columns, PyDict data)
    {
        var output = new List<KeyValuePair<string, PyJson>>();
        foreach (var (key, raw) in data.Items)
        {
            if (!columns.TryGetValue(key, out var column))
            {
                continue;
            }

            output.Add(new(key, column.Kind == ColumnKind.DateTime ? ParsePyDateTimeValue(raw) : raw));
        }

        return output;
    }

    private static Dictionary<string, PyJson> ToKwargs(Dictionary<string, Column> columns, PyDict data)
    {
        var dict = new Dictionary<string, PyJson>(StringComparer.Ordinal);
        foreach (var (key, value) in ToKwargsList(columns, data))
        {
            dict[key] = value;
        }

        return dict;
    }

    /// <summary>A parsed timestamp is carried as a <see cref="PyDateTimeValue"/>.</summary>
    private static PyJson ParsePyDateTimeValue(PyJson raw)
    {
        if (raw is not PyStr text)
        {
            return PyNull.Instance;
        }

        var replaced = text.Value.Replace("Z", "+00:00", StringComparison.Ordinal);
        return PyDateTime.TryFromIsoFormat(replaced, out var parsed)
            ? new PyDateTimeValue(parsed)
            : throw new PyValueErrorException($"Invalid isoformat string: {PyConvert.ReprString(replaced)}");
    }

    private static async Task<long> InsertAsync(UnitOfWork uow, string table, Dictionary<string, Column> columns, Dictionary<string, PyJson> kwargs)
    {
        if (kwargs.Count == 0)
        {
            var emptyId = await uow.ExecuteScalarWriteAsync($"INSERT INTO {table} DEFAULT VALUES RETURNING id").ConfigureAwait(false);
            return Convert.ToInt64(emptyId, CultureInfo.InvariantCulture);
        }

        var names = kwargs.Keys.ToList();
        var parameters = names.Select(name => ($"${name}", Bind(columns[name], kwargs[name]))).ToArray();
        var id = await uow.ExecuteScalarWriteAsync(
            $"INSERT INTO {table} ({string.Join(", ", names.Select(n => $"\"{n}\""))}) VALUES ({string.Join(", ", names.Select(n => "$" + n))}) RETURNING id",
            parameters).ConfigureAwait(false);
        return Convert.ToInt64(id, CultureInfo.InvariantCulture);
    }

    private static object? Bind(Column column, PyJson value)
    {
        switch (column.Kind)
        {
            case ColumnKind.DateTime:
                return value is PyDateTimeValue dt ? dt.Value.ToSqlite() : DBNull.Value;
            case ColumnKind.Boolean:
                return value switch
                {
                    PyNull => DBNull.Value,
                    PyBool b => b.Value ? 1L : 0L,
                    PyInt i when i.Value.IsZero || i.Value.IsOne => (long)i.Value,
                    PyFloat f when f.Value is 0.0 or 1.0 => (long)f.Value,
                    _ => throw new PyTypeErrorException($"Not a boolean value: {PyConvert.Repr(value)}"),
                };
            default:
                return PyConvert.ToDatabase(value);
        }
    }

    private static bool PythonEquals(ColumnKind kind, PyJson? loaded, PyJson assigned)
    {
        loaded ??= PyNull.Instance;
        if (kind == ColumnKind.DateTime || loaded is PyDateTimeValue || assigned is PyDateTimeValue)
        {
            return (loaded, assigned) switch
            {
                (PyNull, PyNull) => true,
                (PyDateTimeValue a, PyDateTimeValue b) => a.Value.IsAware == b.Value.IsAware &&
                    (a.Value.IsAware ? a.Value.AsUtc == b.Value.AsUtc : a.Value.Clock == b.Value.Clock),
                _ => false,
            };
        }

        return (loaded, assigned) switch
        {
            (PyNull, PyNull) => true,
            (PyStr a, PyStr b) => a.Value == b.Value,
            _ when Numeric(loaded) is { } x && Numeric(assigned) is { } y => x == y,
            _ => false,
        };
    }

    private static double? Numeric(PyJson value) => value switch
    {
        PyBool b => b.Value ? 1 : 0,
        PyInt i => (double)i.Value,
        PyFloat f => f.Value,
        _ => null,
    };

    private static async Task<Dictionary<string, Column>> ColumnsAsync(UnitOfWork uow, string table)
    {
        var columns = await uow.QueryAsync(
            $"PRAGMA table_info({table})",
            reader => new Column(
                SqliteValues.GetString(reader, 1),
                SqliteValues.GetString(reader, 2).ToUpperInvariant() switch
                {
                    "BOOLEAN" => ColumnKind.Boolean,
                    "DATETIME" => ColumnKind.DateTime,
                    _ => ColumnKind.Raw,
                })).ConfigureAwait(false);
        var ordered = new Dictionary<string, Column>(StringComparer.Ordinal);
        foreach (var column in columns)
        {
            ordered[column.Name] = column;
        }

        return ordered;
    }

    /// <summary><c>orm_row_to_dict</c> for every matching row, columns in table order.</summary>
    private static async Task<List<PyJson>> ReadRowsAsync(UnitOfWork uow, string table, string clause)
    {
        var columns = await ColumnsAsync(uow, table).ConfigureAwait(false);
        var names = columns.Keys.ToList();
        return await uow.QueryAsync<PyJson>(
            $"SELECT {string.Join(", ", names.Select(n => $"\"{n}\""))} FROM {table} {clause}",
            reader =>
            {
                var row = new PyDict();
                for (var i = 0; i < names.Count; i++)
                {
                    row.Set(names[i], SerializeStored(columns[names[i]], reader.GetValue(i)));
                }

                return row;
            }).ConfigureAwait(false);
    }

    private static async Task<Dictionary<string, PyJson>?> ReadTypedRowAsync(UnitOfWork uow, string table, Dictionary<string, Column> columns, PyJson pk)
    {
        var names = columns.Keys.ToList();
        var rows = await uow.QueryAsync(
            $"SELECT {string.Join(", ", names.Select(n => $"\"{n}\""))} FROM {table} WHERE id = $pk",
            reader =>
            {
                var row = new Dictionary<string, PyJson>(StringComparer.Ordinal);
                for (var i = 0; i < names.Count; i++)
                {
                    row[names[i]] = LoadStored(columns[names[i]], reader.GetValue(i));
                }

                return row;
            },
            ("$pk", PyConvert.ToDatabase(pk))).ConfigureAwait(false);
        return rows.Count > 0 ? rows[0] : null;
    }

    private static PyJson LoadStored(Column column, object value)
    {
        if (value is DBNull)
        {
            return PyNull.Instance;
        }

        return column.Kind switch
        {
            ColumnKind.Boolean => PyJson.Of(PyConvert.FromDatabase(value).IsTruthy),
            ColumnKind.DateTime => PyDateTime.TryFromIsoFormat(Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty, out var parsed)
                ? new PyDateTimeValue(parsed)
                : throw new FormatException("Invalid isoformat string in the database."),
            _ => PyConvert.FromDatabase(value),
        };
    }

    private static PyJson SerializeStored(Column column, object value)
    {
        var loaded = LoadStored(column, value);
        return loaded is PyDateTimeValue dt ? PyJson.Of(dt.Value.AstimezoneUtc().IsoFormat()) : loaded;
    }
}
