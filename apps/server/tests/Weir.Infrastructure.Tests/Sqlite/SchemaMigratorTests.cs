using Microsoft.Data.Sqlite;
using Weir.Infrastructure.Scheduling;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Sqlite;

public sealed class SchemaMigratorTests
{
    [Fact]
    public void An_alembic_database_at_the_frozen_baseline_is_upgraded_to_head()
    {
        // Before #557, the .NET head *was* the frozen Alembic baseline, so an Alembic-created database
        // needed no change at all. #557 lifted the freeze and added migrations past it, so this database
        // is now merely at the oldest revision this build knows how to reach, and EnsureAtHead upgrades
        // it in place instead of adopting it unchanged.
        using var temp = new TempDirectory();
        var path = temp.Join("weir.sqlite3");
        SchemaSnapshot.Execute(path, File.ReadAllText(RepositoryPaths.AlembicHeadReference));

        var database = new SqliteDatabase(path);
        var outcome = new SchemaMigrator(database).EnsureAtHead();
        database.ClearPool();

        Assert.Equal(SchemaStartupOutcome.Upgraded, outcome);
        Assert.Equal(1, SchemaSnapshot.ScalarLong(path, $"SELECT COUNT(*) FROM alembic_version WHERE version_num = '{SchemaMigrator.HeadRevision}'"));

        // Matches a database created fresh at head, once the seeded suite_settings row's timestamps
        // (masked by SchemaSnapshot) and the fact a fresh install seeds no libraries/rule sets are allowed for.
        using var freshTemp = new TempDirectory();
        var freshPath = freshTemp.Join("fresh.sqlite3");
        var freshDatabase = new SqliteDatabase(freshPath);
        Assert.Equal(SchemaStartupOutcome.Created, new SchemaMigrator(freshDatabase).EnsureAtHead());
        freshDatabase.ClearPool();
        Assert.Equal(SchemaSnapshot.Describe(freshPath), SchemaSnapshot.Describe(path));
    }

    [Fact]
    public void A_database_this_build_created_is_current_on_the_next_start()
    {
        using var temp = new TempDirectory();
        var database = new SqliteDatabase(temp.Join("weir.sqlite3"));
        Assert.Equal(SchemaStartupOutcome.Created, new SchemaMigrator(database).EnsureAtHead());
        Assert.Equal(SchemaStartupOutcome.AlreadyCurrent, new SchemaMigrator(database).EnsureAtHead());
        Assert.Equal(1, SchemaSnapshot.ScalarLong(database.DatabasePath, $"SELECT COUNT(*) FROM alembic_version WHERE version_num = '{SchemaMigrator.HeadRevision}'"));
        database.ClearPool();
    }

    [Fact]
    public void An_older_alembic_revision_is_refused_untouched()
    {
        using var temp = new TempDirectory();
        var path = AlembicDatabaseAt(temp, "0035_direct_play_facts");
        var before = SchemaSnapshot.Describe(path);

        var database = new SqliteDatabase(path);
        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(database).EnsureAtHead());
        database.ClearPool();

        Assert.Equal(SchemaMismatchKind.BehindHead, error.Kind);
        Assert.Equal(
            "Database revision '0035_direct_play_facts' was created by an older Weir release. " +
            $"This build requires schema revision '{SchemaMigrator.HeadRevision}' and cannot upgrade older databases itself. " +
            "Start the previous Weir release once so it migrates the database, then start this build again.",
            error.Message);
        Assert.Equal(before, SchemaSnapshot.Describe(path));
    }

    [Fact]
    public void An_unknown_revision_is_refused_with_the_python_message()
    {
        using var temp = new TempDirectory();
        var path = AlembicDatabaseAt(temp, "0099_from_the_future");

        var database = new SqliteDatabase(path);
        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(database).EnsureAtHead());
        database.ClearPool();

        Assert.Equal(SchemaMismatchKind.UnknownRevision, error.Kind);
        Assert.Equal(
            $"Database revision '0099_from_the_future' is not recognized by this Weir build (expected head '{SchemaMigrator.HeadRevision}'). " +
            "The database may come from a newer release; upgrade the application or restore a backup that matches this version.",
            error.Message);
    }

    [Fact]
    public void Tables_without_a_recorded_revision_are_refused()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("other.sqlite3");
        SchemaSnapshot.Execute(path, "CREATE TABLE something_else (id INTEGER PRIMARY KEY);");

        var database = new SqliteDatabase(path);
        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(database).EnsureAtHead());
        database.ClearPool();

        Assert.Equal(SchemaMismatchKind.Unversioned, error.Kind);
        Assert.StartsWith(
            $"No Alembic revision is recorded for this database (migrations have not been applied). This build requires schema revision '{SchemaMigrator.HeadRevision}'.",
            error.Message,
            StringComparison.Ordinal);
        Assert.Equal(1, SchemaSnapshot.ScalarLong(path, "SELECT COUNT(*) FROM sqlite_master"));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void An_existing_file_without_a_schema_is_refused_and_left_empty(bool zeroBytes)
    {
        // Python refuses any unversioned database; only a missing file is a new install.
        using var temp = new TempDirectory();
        var path = temp.Join("weir.sqlite3");
        if (zeroBytes)
        {
            File.WriteAllBytes(path, []);
        }
        else
        {
            SchemaSnapshot.Execute(path, "PRAGMA user_version = 0; VACUUM;");
        }

        var database = new SqliteDatabase(path);
        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(database).EnsureAtHead());
        database.ClearPool();

        Assert.Equal(SchemaMismatchKind.Unversioned, error.Kind);
        Assert.StartsWith("No Alembic revision is recorded for this database", error.Message, StringComparison.Ordinal);
        Assert.Equal(0, SchemaSnapshot.ScalarLong(path, "SELECT COUNT(*) FROM sqlite_master"));
        if (zeroBytes)
        {
            Assert.False(File.Exists(path + "-wal"));
        }
    }

    [Fact]
    public void A_missing_file_is_created_at_head()
    {
        using var temp = new TempDirectory();
        var path = temp.Join("weir.sqlite3");

        var database = new SqliteDatabase(path);
        Assert.Equal(SchemaStartupOutcome.Created, new SchemaMigrator(database).EnsureAtHead());
        database.ClearPool();

        Assert.Equal(1, SchemaSnapshot.ScalarLong(path, "SELECT COUNT(*) FROM alembic_version"));
    }

    [Fact]
    public void An_empty_version_table_is_unversioned_and_several_rows_are_incompatible()
    {
        using var temp = new TempDirectory();
        var empty = temp.Join("empty.sqlite3");
        SchemaSnapshot.Execute(empty, "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);");
        var emptyDatabase = new SqliteDatabase(empty);
        Assert.Equal(
            SchemaMismatchKind.Unversioned,
            Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(emptyDatabase).EnsureAtHead()).Kind);
        emptyDatabase.ClearPool();

        var several = temp.Join("several.sqlite3");
        SchemaSnapshot.Execute(several, "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL); INSERT INTO alembic_version VALUES ('a'), ('b');");
        var severalDatabase = new SqliteDatabase(several);
        var error = Assert.Throws<DatabaseSchemaMismatchException>(() => new SchemaMigrator(severalDatabase).EnsureAtHead());
        severalDatabase.ClearPool();
        Assert.Equal(SchemaMismatchKind.Incompatible, error.Kind);
        Assert.Contains("('a', 'b')", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Connections_apply_the_python_engine_pragmas()
    {
        using var temp = new TempDirectory();
        var database = new SqliteDatabase(temp.Join("weir.sqlite3"));
        using (var connection = database.Open())
        {
            Assert.Equal("wal", Pragma(connection, "journal_mode"));
            Assert.Equal("1", Pragma(connection, "foreign_keys"));
            Assert.Equal("30000", Pragma(connection, "busy_timeout"));
            Assert.Equal("1", Pragma(connection, "synchronous"));
        }

        database.ClearPool();
    }

    [Fact]
    public async Task The_health_probe_restores_the_busy_timeout()
    {
        using var temp = new TempDirectory();
        var database = new SqliteDatabase(temp.Join("weir.sqlite3"));
        Assert.True(await database.IsConnectedAsync());
        using (var connection = database.Open())
        {
            Assert.Equal("30000", Pragma(connection, "busy_timeout"));
        }

        database.ClearPool();
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
        Assert.Equal(30, await LogRetentionTask.ReadKeepDaysAsync(database));

        using (var connection = database.Open())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "UPDATE suite_settings SET log_retention_days = 0";
            command.ExecuteNonQuery();
        }

        Assert.Equal(1, await LogRetentionTask.ReadKeepDaysAsync(database));

        using (var connection = database.Open())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "DELETE FROM suite_settings";
            command.ExecuteNonQuery();
        }

        // ensure_suite_settings_row: a missing row is created with its defaults.
        Assert.Equal(30, await LogRetentionTask.ReadKeepDaysAsync(database));
        using (var connection = database.Open())
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "SELECT count(*) FROM suite_settings";
            Assert.Equal(1L, command.ExecuteScalar());
        }

        database.ClearPool();
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
