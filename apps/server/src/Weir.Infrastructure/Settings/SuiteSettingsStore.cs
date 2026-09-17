using Microsoft.Data.Sqlite;
using Weir.Core.Settings;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Settings;

/// <summary>The <c>suite_settings</c> singleton (port of <c>ensure_suite_settings_row</c> and the ORM updates to it).</summary>
public static class SuiteSettingsStore
{
    private const string Columns =
        "product_display_name, signed_in_home_notice, setup_wizard_state, app_timezone, log_retention_days, activity_retention_days, " +
        "direct_play_devices, configuration_backup_enabled, configuration_backup_interval_hours, configuration_backup_preferred_time, " +
        "configuration_backup_last_run_at, processing_paused, processing_paused_until, scan_while_paused, " +
        "metadata_provider, metadata_provider_base_url, metadata_provider_key_ciphertext, updated_at";

    public static Task<SuiteSettingsRecord?> GetAsync(UnitOfWork uow)
    {
        ArgumentNullException.ThrowIfNull(uow);
        return uow.QuerySingleAsync($"SELECT {Columns} FROM suite_settings WHERE suite_settings.id = 1", Read);
    }

    /// <summary><c>ensure_suite_settings_row</c>.</summary>
    public static async Task<SuiteSettingsRecord> EnsureAsync(UnitOfWork uow)
    {
        var row = await GetAsync(uow).ConfigureAwait(false);
        if (row is not null)
        {
            return row;
        }

        var users = await AuthStore.CountUsersAsync(uow).ConfigureAwait(false);
        await uow.ExecuteAsync(
            "INSERT INTO suite_settings (id, product_display_name, signed_in_home_notice, setup_wizard_state, app_timezone, log_retention_days, " +
            "activity_retention_days, configuration_backup_enabled, configuration_backup_interval_hours, configuration_backup_preferred_time, " +
            "configuration_backup_last_run_at) VALUES (1, 'Weir', NULL, $wizard, 'UTC', 30, 90, 0, 24, '02:00', NULL)",
            ("$wizard", SuiteSettingsRules.DefaultSetupWizardState(users))).ConfigureAwait(false);
        return await GetAsync(uow).ConfigureAwait(false) ?? throw new InvalidOperationException("suite_settings row was not created.");
    }

    /// <summary>
    /// Write the columns that differ between <paramref name="before"/> and <paramref name="after"/>, bumping
    /// <c>updated_at</c> when anything changed (SQLAlchemy's <c>onupdate=func.now()</c>).
    /// </summary>
    public static async Task UpdateAsync(UnitOfWork uow, SuiteSettingsRecord before, SuiteSettingsRecord after)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(before);
        ArgumentNullException.ThrowIfNull(after);
        var sets = new List<string>();
        var parameters = new List<(string, object?)>();
        void Compare<T>(string column, T left, T right, Func<T, object?> toDb)
        {
            if (!EqualityComparer<T>.Default.Equals(left, right))
            {
                sets.Add($"{column}=${column}");
                parameters.Add(($"${column}", toDb(right)));
            }
        }

        Compare("product_display_name", before.ProductDisplayName, after.ProductDisplayName, v => v);
        Compare("signed_in_home_notice", before.SignedInHomeNotice, after.SignedInHomeNotice, v => v);
        Compare("setup_wizard_state", before.SetupWizardState, after.SetupWizardState, v => v);
        Compare("app_timezone", before.AppTimezone, after.AppTimezone, v => v);
        Compare("log_retention_days", before.LogRetentionDays, after.LogRetentionDays, v => v);
        Compare("activity_retention_days", before.ActivityRetentionDays, after.ActivityRetentionDays, v => v);
        Compare("configuration_backup_enabled", before.ConfigurationBackupEnabled, after.ConfigurationBackupEnabled, v => v ? 1 : 0);
        Compare("configuration_backup_interval_hours", before.ConfigurationBackupIntervalHours, after.ConfigurationBackupIntervalHours, v => v);
        Compare("configuration_backup_preferred_time", before.ConfigurationBackupPreferredTime, after.ConfigurationBackupPreferredTime, v => v);
        Compare("configuration_backup_last_run_at", before.ConfigurationBackupLastRunAt, after.ConfigurationBackupLastRunAt, v => SqliteValues.ToSqlite(v));
        Compare("processing_paused", before.ProcessingPaused, after.ProcessingPaused, v => v ? 1 : 0);
        Compare("processing_paused_until", before.ProcessingPausedUntil, after.ProcessingPausedUntil, v => SqliteValues.ToSqlite(v));
        Compare("scan_while_paused", before.ScanWhilePaused, after.ScanWhilePaused, v => v ? 1 : 0);
        Compare("direct_play_devices", before.DirectPlayDevices, after.DirectPlayDevices, v => v);
        Compare("metadata_provider", before.MetadataProvider, after.MetadataProvider, v => v);
        Compare("metadata_provider_base_url", before.MetadataProviderBaseUrl, after.MetadataProviderBaseUrl, v => v);
        Compare("metadata_provider_key_ciphertext", before.MetadataProviderKeyCiphertext, after.MetadataProviderKeyCiphertext, v => v);
        if (sets.Count == 0)
        {
            return;
        }

        sets.Add("updated_at=CURRENT_TIMESTAMP");
        await uow.ExecuteAsync($"UPDATE suite_settings SET {string.Join(", ", sets)} WHERE suite_settings.id = 1", [.. parameters]).ConfigureAwait(false);
    }

    private static SuiteSettingsRecord Read(SqliteDataReader reader) => new()
    {
        ProductDisplayName = SqliteValues.GetString(reader, 0),
        SignedInHomeNotice = SqliteValues.GetStringOrNull(reader, 1),
        SetupWizardState = SqliteValues.GetString(reader, 2),
        AppTimezone = SqliteValues.GetString(reader, 3),
        LogRetentionDays = SqliteValues.GetInt64(reader, 4),
        ActivityRetentionDays = SqliteValues.GetInt64(reader, 5),
        DirectPlayDevices = SqliteValues.GetString(reader, 6),
        ConfigurationBackupEnabled = SqliteValues.GetBool(reader, 7),
        ConfigurationBackupIntervalHours = SqliteValues.GetInt64(reader, 8),
        ConfigurationBackupPreferredTime = SqliteValues.GetString(reader, 9),
        ConfigurationBackupLastRunAt = SqliteValues.GetDateTimeOrNull(reader, 10),
        ProcessingPaused = SqliteValues.GetBool(reader, 11),
        ProcessingPausedUntil = SqliteValues.GetDateTimeOrNull(reader, 12),
        ScanWhilePaused = SqliteValues.GetBool(reader, 13),
        MetadataProvider = SqliteValues.GetString(reader, 14),
        MetadataProviderBaseUrl = SqliteValues.GetString(reader, 15),
        MetadataProviderKeyCiphertext = SqliteValues.GetString(reader, 16),
        UpdatedAt = SqliteValues.GetDateTime(reader, 17),
    };
}
