using System.Reflection;
using Microsoft.Data.Sqlite;

namespace Weir.Infrastructure.Sqlite;

/// <summary>One numbered SQL migration and the <c>alembic_version</c> value it leaves behind.</summary>
/// <param name="Number">Order of application.</param>
/// <param name="Revision">The revision recorded once the script has run.</param>
/// <param name="ResourceName">The embedded <c>Migrations/*.sql</c> file.</param>
public sealed record SchemaMigration(int Number, string Revision, string ResourceName);

/// <summary>Why the database could not be used, mirroring the Python <c>DatabaseSchemaMismatch.kind</c> values where they apply.</summary>
public enum SchemaMismatchKind
{
    /// <summary>The file exists but no revision is recorded (including an empty file).</summary>
    Unversioned,

    /// <summary>A revision this build has never heard of (probably a newer release).</summary>
    UnknownRevision,

    /// <summary>An older Alembic revision: the Python release must migrate it first.</summary>
    BehindHead,

    /// <summary>The version table is malformed.</summary>
    Incompatible,
}

/// <summary>The database cannot be opened by this build. The message is for the operator.</summary>
public sealed class DatabaseSchemaMismatchException : Exception
{
    public DatabaseSchemaMismatchException()
    {
    }

    public DatabaseSchemaMismatchException(string message)
        : base(message)
    {
    }

    public DatabaseSchemaMismatchException(string message, Exception innerException)
        : base(message, innerException)
    {
    }

    public DatabaseSchemaMismatchException(string message, SchemaMismatchKind kind)
        : base(message)
    {
        Kind = kind;
    }

    public SchemaMismatchKind Kind { get; }
}

/// <summary>What startup did to the database.</summary>
public enum SchemaStartupOutcome
{
    /// <summary>The file did not exist; the schema was created and seeded.</summary>
    Created,

    /// <summary>The database was already at this build's revision (created by Alembic or by an earlier .NET start); nothing was written.</summary>
    AlreadyCurrent,

    /// <summary>
    /// The database was at an earlier revision this build knows how to reach (created by Alembic at the
    /// frozen baseline, or by an earlier .NET build at one of its own migrations): every migration after
    /// that revision, in order, was applied to bring it to head.
    /// </summary>
    Upgraded,
}

/// <summary>
/// Brings the database to this build's schema, or refuses to touch it.
/// </summary>
/// <remarks>
/// <para>
/// <b>Version ledger:</b> the .NET server reuses Alembic's own <c>alembic_version</c> table
/// instead of adding a <c>schema_version</c> table. The schema is part of the contract that must
/// not move (ADR-0017), so a database created by either backend is byte-for-byte the same kind of
/// database and either backend can open it, which the contract suite relies on; an existing
/// install is adopted with no write at all. Each migration names the revision it leaves behind;
/// after the switch (#523) new migrations continue Alembic's numbering (<c>0037_…</c>).
/// </para>
/// <para>
/// <b>On startup:</b> a missing database file is created at head; a database whose recorded revision is
/// head is adopted unchanged; a database recorded at any earlier revision in <see cref="Migrations"/> —
/// the frozen Alembic baseline, or one of this build's own earlier migrations — is upgraded in place by
/// applying every migration after it, in order, in one transaction (issue #557 lifted the freeze and
/// this is the "SchemaMigrator taught to upgrade a database at the previous head" the schema docs
/// promise); anything else, including an existing file with no schema or a genuinely pre-baseline
/// Alembic revision, is refused with a message and no change — the pre-baseline case still needs the
/// retired Python backend's own Alembic to reach the baseline first.
/// </para>
/// </remarks>
public sealed class SchemaMigrator
{
    public static readonly IReadOnlyList<SchemaMigration> Migrations =
    [
        new(1, "0036_drop_pruner_tables", "Weir.Infrastructure.Migrations.0001_baseline_0036_drop_pruner_tables.sql"),
        new(2, "0037_refiner_rule_set_extra_columns", "Weir.Infrastructure.Migrations.0002_refiner_rule_set_extra_columns.sql"),
        new(3, "0038_library_mode_settings", "Weir.Infrastructure.Migrations.0003_library_mode_settings.sql"),
        new(4, "0039_library_files", "Weir.Infrastructure.Migrations.0004_library_files.sql"),
        new(5, "0040_library_swaps", "Weir.Infrastructure.Migrations.0005_library_swaps.sql"),
        new(6, "0041_removed_tracks", "Weir.Infrastructure.Migrations.0006_removed_tracks.sql"),
        new(7, "0042_library_file_facets", "Weir.Infrastructure.Migrations.0007_library_file_facets.sql"),
        new(8, "0043_remux_writer", "Weir.Infrastructure.Migrations.0008_remux_writer.sql"),
    ];

    /// <summary>
    /// The schema before issue #557's migrations (the frozen Alembic-head shape every released Weir up to
    /// and including #523's switch-over could create): the checked-in <c>schema/alembic-head.sql</c>
    /// reference and <c>SchemaParityTests</c> stay pinned to this revision on purpose (see
    /// apps/server/README.md, "Schema") rather than to the moving <see cref="HeadRevision"/>, since #557
    /// deliberately diverges from the frozen Alembic shape.
    /// </summary>
    public static string BaselineRevision => Migrations[0].Revision;

    /// <summary>
    /// Alembic revisions before the baseline, oldest first. A database at one of these was made by
    /// an older Python release that knows how to upgrade it.
    /// </summary>
    public static readonly IReadOnlyList<string> AlembicRevisionsBeforeBaseline =
    [
        "0001_weir_initial_schema",
        "0002_weir_schema_tip",
        "0003_pruner_auto_apply_snapshot_limits",
        "0004_pruner_uniqueness_constraints",
        "0005_refiner_guardrail_settings",
        "0006_trusted_device_sessions",
        "0007_indexes_and_retry_backoff",
        "0008_notification_channels",
        "0009_media_manager_connections",
        "0010_drop_subber_tables",
        "0011_refiner_libraries",
        "0012_refiner_file_states",
        "0013_refiner_file_settling",
        "0014_refiner_watcher",
        "0015_schedules_and_pause",
        "0016_runner_units",
        "0017_retry_and_sweeps",
        "0018_file_processing_log",
        "0019_track_sorters",
        "0020_metadata_rules",
        "0021_sidecar_migration",
        "0022_output_collision_policy",
        "0023_hardware_acceleration",
        "0024_metadata_provider",
        "0025_drop_refiner_singletons",
        "0026_session_client_labels",
        "0027_refiner_rejected_file_action",
        "0028_refiner_detection_windows",
        "0029_case_insensitive_usernames",
        "0030_refiner_file_media_facts",
        "0031_refiner_failure_policy",
        "0032_media_manager_handoffs",
        "0033_refiner_library_media_type",
        "0034_activity_history_facts",
        "0035_direct_play_facts",
    ];

    public static string HeadRevision => Migrations[^1].Revision;

    private readonly SqliteDatabase _database;

    public SchemaMigrator(SqliteDatabase database)
    {
        _database = database;
    }

    public SchemaStartupOutcome EnsureAtHead()
    {
        // Only a missing file is a new install. A file that exists but holds no schema was made by
        // something else (or by a start that failed half-way); Python refuses it as unversioned, and so
        // does this build, without opening it (opening would switch it to WAL).
        var existed = File.Exists(_database.DatabasePath);
        if (existed && new FileInfo(_database.DatabasePath).Length == 0)
        {
            throw UnversionedError();
        }

        using var connection = _database.Open();
        var userObjects = ScalarLong(connection, "SELECT COUNT(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'");
        if (userObjects == 0)
        {
            if (existed)
            {
                throw UnversionedError();
            }

            ApplyAll(connection);
            return SchemaStartupOutcome.Created;
        }

        var current = ReadRecordedRevision(connection);
        if (current == HeadRevision)
        {
            return SchemaStartupOutcome.AlreadyCurrent;
        }

        var currentIndex = Migrations.ToList().FindIndex(m => m.Revision == current);
        if (currentIndex >= 0)
        {
            ApplyRange(connection, Migrations.Skip(currentIndex + 1), HeadRevision);
            return SchemaStartupOutcome.Upgraded;
        }

        if (AlembicRevisionsBeforeBaseline.Contains(current, StringComparer.Ordinal))
        {
            throw new DatabaseSchemaMismatchException(
                $"Database revision {Quote(current!)} was created by an older Weir release. " +
                $"This build requires schema revision {Quote(HeadRevision)} and cannot upgrade older databases itself. " +
                "Start the previous Weir release once so it migrates the database, then start this build again.",
                SchemaMismatchKind.BehindHead);
        }

        throw new DatabaseSchemaMismatchException(
            $"Database revision {Quote(current!)} is not recognized by this Weir build " +
            $"(expected head {Quote(HeadRevision)}). The database may come from a newer release; " +
            "upgrade the application or restore a backup that matches this version.",
            SchemaMismatchKind.UnknownRevision);
    }

    internal static string ReadMigrationSql(SchemaMigration migration)
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(migration.ResourceName)
            ?? throw new InvalidOperationException($"Migration resource {migration.ResourceName} is missing from this build.");
        using var reader = new StreamReader(stream);
        // Line endings are normalized so sqlite_master holds the same text as an Alembic-created database.
        return reader.ReadToEnd().Replace("\r\n", "\n", StringComparison.Ordinal);
    }

    /// <summary>
    /// Builds a fresh database at exactly <see cref="BaselineRevision"/> (the frozen Alembic-head shape),
    /// ignoring every migration #557 and later added. Test-only: <c>SchemaParityTests</c> uses this to keep
    /// comparing against <c>alembic-head.sql</c> without that reference file ever changing.
    /// </summary>
    public SchemaStartupOutcome EnsureAtBaseline()
    {
        using var connection = _database.Open();
        ApplyRange(connection, Migrations.Take(1), BaselineRevision);
        return SchemaStartupOutcome.Created;
    }

    private static void ApplyAll(SqliteConnection connection) => ApplyRange(connection, Migrations.OrderBy(m => m.Number), HeadRevision);

    private static void ApplyRange(SqliteConnection connection, IEnumerable<SchemaMigration> migrations, string revision)
    {
        using var transaction = connection.BeginTransaction();
        using (var deferForeignKeys = connection.CreateCommand())
        {
            deferForeignKeys.Transaction = transaction;
            deferForeignKeys.CommandText = "PRAGMA defer_foreign_keys=ON";
            deferForeignKeys.ExecuteNonQuery();
        }

        foreach (var migration in migrations)
        {
            using var command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = ReadMigrationSql(migration);
            command.ExecuteNonQuery();
        }

        using (var record = connection.CreateCommand())
        {
            record.Transaction = transaction;
            record.CommandText = "DELETE FROM alembic_version; INSERT INTO alembic_version (version_num) VALUES ($revision);";
            record.Parameters.AddWithValue("$revision", revision);
            record.ExecuteNonQuery();
        }

        transaction.Commit();
    }

    private static string? ReadRecordedRevision(SqliteConnection connection)
    {
        var hasTable = ScalarLong(
            connection,
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'") > 0;
        var revisions = new List<string>();
        if (hasTable)
        {
            using var command = connection.CreateCommand();
            command.CommandText = "SELECT version_num FROM alembic_version";
            using var reader = command.ExecuteReader();
            while (reader.Read())
            {
                revisions.Add(reader.GetString(0));
            }
        }

        return revisions.Count switch
        {
            0 => throw UnversionedError(),
            1 => revisions[0],
            _ => throw new DatabaseSchemaMismatchException(
                $"Database records several schema revisions ({string.Join(", ", revisions.Select(Quote))}); " +
                $"this build requires exactly {Quote(HeadRevision)}. Restore a backup that matches this version.",
                SchemaMismatchKind.Incompatible),
        };
    }

    /// <summary>Python's <c>kind="unversioned"</c> refusal, with this build's advice instead of Alembic's.</summary>
    private static DatabaseSchemaMismatchException UnversionedError() => new(
        "No Alembic revision is recorded for this database (migrations have not been applied). " +
        $"This build requires schema revision {Quote(HeadRevision)}. " +
        "Weir only opens a database that Weir created: point WEIR_DB_PATH at the right file, " +
        "restore a backup, or move this file aside so Weir creates a new one.",
        SchemaMismatchKind.Unversioned);

    private static long ScalarLong(SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt64(command.ExecuteScalar(), System.Globalization.CultureInfo.InvariantCulture);
    }

    /// <summary>Python's <c>repr()</c> of a revision string, as the Python messages print it.</summary>
    private static string Quote(string value) => $"'{value}'";
}
