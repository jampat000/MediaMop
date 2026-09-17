using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Sqlite;

/// <summary>
/// The .NET migrations create exactly the database the retired Python backend's Alembic head created.
/// The reference, <c>schema/alembic-head.sql</c>, is <c>sqlite_master</c> plus seeded rows dumped from a
/// real <c>alembic upgrade head</c> before the Python backend was deleted (#523). It is frozen: a new .NET
/// migration changes the schema on purpose, and this test then compares against the baseline migration only
/// (see apps/server/README.md, "Schema").
/// </summary>
public sealed class SchemaParityTests
{
    [Fact]
    public void Migrations_create_the_alembic_head_schema_and_seed_rows()
    {
        using var temp = new TempDirectory();
        var alembic = temp.Join("alembic.sqlite3");
        var dotnet = temp.Join("dotnet.sqlite3");
        SchemaSnapshot.Execute(alembic, File.ReadAllText(RepositoryPaths.AlembicHeadReference));

        var database = new SqliteDatabase(dotnet);
        var outcome = new SchemaMigrator(database).EnsureAtHead();
        database.ClearPool();

        Assert.Equal(SchemaStartupOutcome.Created, outcome);
        var expected = SchemaSnapshot.Describe(alembic);
        var actual = SchemaSnapshot.Describe(dotnet);
        Assert.Contains("object table users on users:", expected, StringComparison.Ordinal);
        Assert.Contains("object index ux_users_username_lower on users:", expected, StringComparison.Ordinal);
        Assert.Contains("foreign_key refiner_libraries", expected, StringComparison.Ordinal);
        Assert.Contains("row suite_settings:", expected, StringComparison.Ordinal);
        Assert.Equal(expected, actual);
    }

    [Fact]
    public void Reference_names_the_revision_the_migrations_record()
    {
        var header = File.ReadLines(RepositoryPaths.AlembicHeadReference).Take(5).ToList();
        Assert.Contains($"-- alembic_revision: {SchemaMigrator.HeadRevision}", header);
    }
}
