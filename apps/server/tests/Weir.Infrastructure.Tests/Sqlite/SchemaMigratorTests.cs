using Microsoft.Data.Sqlite;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Sqlite;

public sealed class SchemaMigratorTests
{
    [Fact]
    public void An_alembic_database_at_head_is_adopted_without_any_change()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("weir.sqlite3");
        SchemaSnapshot.Execute(path, File.ReadAllText(RepositoryPaths.AlembicHeadReference));
        var before = SchemaSnapshot.Describe(path);
        var schemaVersionBefore = SchemaSnapshot.ScalarLong(path, "PRAGMA schema_version");
        var changesBefore = SchemaSnapshot.ScalarLong(path, "SELECT COUNT(*) FROM suite_settings");

        var outcome = new SchemaMigrator(new SqliteDatabase(path)).EnsureAtHead();
        SqliteConnection.ClearAllPools();

        Assert.Equal(SchemaStartupOutcome.AlreadyCurrent, outcome);
        Assert.Equal(before, SchemaSnapshot.Describe(path));
        Assert.Equal(schemaVersionBefore, SchemaSnapshot.ScalarLong(path, "PRAGMA schema_version"));
        Assert.Equal(changesBefore, SchemaSnapshot.ScalarLong(path, "SELECT COUNT(*) FROM suite_settings"));
    }

    [Fact]
    public void A_database_this_build_created_is_current_on_the_next_start()
    {
        using var temp = new TempDirectory();
        var database = new SqliteDatabase(temp.Join("weir.sqlite3"));
        Assert.Equal(SchemaStartupOutcome.Created, new SchemaMigrator(database).EnsureAtHead());
        Assert.Equal(SchemaStartupOutcome.AlreadyCurrent, new SchemaMigrator(database).EnsureAtHead());
        Assert.Equal(1, SchemaSnapshot.ScalarLong(database.DatabasePath, "SELECT COUNT(*) FROM alembic_version WHERE version_num = '0036_drop_pruner_tables'"));
    }

    [Fact]
    public void An_older_alembic_revision_is_refused_untouched()
    {
        using var temp = new TempDirectory();
        var path = AlembicDatabaseAt(temp, "0035_direct_play_facts");
        var before = SchemaSnapshot.Describe(path);

        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(new SqliteDatabase(path)).EnsureAtHead());
        SqliteConnection.ClearAllPools();

        Assert.Equal(SchemaMismatchKind.BehindHead, error.Kind);
        Assert.Equal(
            "Database revision '0035_direct_play_facts' was created by an older Weir release. " +
            "This build requires schema revision '0036_drop_pruner_tables' and cannot upgrade older databases itself. " +
            "Start the previous Weir release once so it migrates the database, then start this build again.",
            error.Message);
        Assert.Equal(before, SchemaSnapshot.Describe(path));
    }

    [Fact]
    public void An_unknown_revision_is_refused_with_the_python_message()
    {
        using var temp = new TempDirectory();
        var path = AlembicDatabaseAt(temp, "0099_from_the_future");

        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(new SqliteDatabase(path)).EnsureAtHead());

        Assert.Equal(SchemaMismatchKind.UnknownRevision, error.Kind);
        Assert.Equal(
            "Database revision '0099_from_the_future' is not recognized by this Weir build (expected head '0036_drop_pruner_tables'). " +
            "The database may come from a newer release; upgrade the application or restore a backup that matches this version.",
            error.Message);
    }

    [Fact]
    public void Tables_without_a_recorded_revision_are_refused()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("other.sqlite3");
        SchemaSnapshot.Execute(path, "CREATE TABLE something_else (id INTEGER PRIMARY KEY);");

        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(new SqliteDatabase(path)).EnsureAtHead());
        SqliteConnection.ClearAllPools();

        Assert.Equal(SchemaMismatchKind.Unversioned, error.Kind);
        Assert.StartsWith(
            "No Alembic revision is recorded for this database (migrations have not been applied). This build requires schema revision '0036_drop_pruner_tables'.",
            error.Message,
            StringComparison.Ordinal);
        Assert.Equal(1, SchemaSnapshot.ScalarLong(path, "SELECT COUNT(*) FROM sqlite_master"));
    }

    [Fact]
    public void An_empty_version_table_is_unversioned_and_several_rows_are_incompatible()
    {
        using var temp = new TempDirectory();
        var empty = temp.Join("empty.sqlite3");
        SchemaSnapshot.Execute(empty, "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);");
        Assert.Equal(
            SchemaMismatchKind.Unversioned,
            Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(new SqliteDatabase(empty)).EnsureAtHead()).Kind);

        var several = temp.Join("several.sqlite3");
        SchemaSnapshot.Execute(several, "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL); INSERT INTO alembic_version VALUES ('a'), ('b');");
        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(new SqliteDatabase(several)).EnsureAtHead());
        Assert.Equal(SchemaMismatchKind.Incompatible, error.Kind);
        Assert.Contains("('a', 'b')", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Connections_apply_the_python_engine_pragmas()
    {
        using var temp = new TempDirectory();
        var database = new SqliteDatabase(temp.Join("weir.sqlite3"));
        using var connection = database.Open();

        Assert.Equal("wal", Pragma(connection, "journal_mode"));
        Assert.Equal("1", Pragma(connection, "foreign_keys"));
        Assert.Equal("30000", Pragma(connection, "busy_timeout"));
        Assert.Equal("1", Pragma(connection, "synchronous"));
    }

    [Fact]
    public async Task The_health_probe_restores_the_busy_timeout()
    {
        using var temp = new TempDirectory();
        var database = new SqliteDatabase(temp.Join("weir.sqlite3"));
        Assert.True(await database.IsConnectedAsync());
        using var connection = database.Open();
        Assert.Equal("30000", Pragma(connection, "busy_timeout"));
    }

    [Fact]
    public async Task The_health_probe_reports_an_unopenable_database_as_disconnected()
    {
        using var temp = new TempDirectory();
        var directoryInsteadOfFile = temp.Join("a-directory");
        Directory.CreateDirectory(directoryInsteadOfFile);
        Assert.False(await new SqliteDatabase(directoryInsteadOfFile).IsConnectedAsync());
    }

    [Fact]
    public async Task Log_retention_days_come_from_suite_settings()
    {
        using var temp = new TempDirectory();
        var database = new SqliteDatabase(temp.Join("weir.sqlite3"));
        new SchemaMigrator(database).EnsureAtHead();
        Assert.Equal(30, await SuiteSettingsQueries.ReadLogRetentionDaysAsync(database));

        using (var connection = database.Open())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "UPDATE suite_settings SET log_retention_days = 0";
            command.ExecuteNonQuery();
        }

        Assert.Equal(1, await SuiteSettingsQueries.ReadLogRetentionDaysAsync(database));

        using (var connection = database.Open())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "DELETE FROM suite_settings";
            command.ExecuteNonQuery();
        }

        Assert.Equal(SuiteSettingsQueries.DefaultLogRetentionDays, await SuiteSettingsQueries.ReadLogRetentionDaysAsync(database));
    }

    private static string AlembicDatabaseAt(TempDirectory temp, string revision)
    {
        var path = temp.Join("alembic.sqlite3");
        SchemaSnapshot.Execute(
            path,
            File.ReadAllText(RepositoryPaths.AlembicHeadReference)
                .Replace("VALUES ('0036_drop_pruner_tables')", $"VALUES ('{revision}')", StringComparison.Ordinal));
        return path;
    }

    private static string Pragma(SqliteConnection connection, string name)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"PRAGMA {name}";
        return Convert.ToString(command.ExecuteScalar(), System.Globalization.CultureInfo.InvariantCulture)!;
    }
}
