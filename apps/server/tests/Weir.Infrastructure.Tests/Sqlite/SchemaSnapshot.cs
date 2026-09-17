using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

namespace Weir.Infrastructure.Tests.Sqlite;

/// <summary>
/// A normalized, comparable description of a SQLite database: every table's columns (name, type,
/// default, not-null, primary-key position), indexes (name, uniqueness, origin, partial, columns
/// and expressions), foreign keys (target, columns, actions), each object's SQL text with
/// whitespace collapsed (which covers CHECK constraints), and the rows in every table with
/// wall-clock timestamps masked.
/// </summary>
internal static partial class SchemaSnapshot
{
    public static string Describe(string databasePath)
    {
        using var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = databasePath, Pooling = false }.ToString());
        connection.Open();
        var builder = new StringBuilder();
        var objects = Query(connection, "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name");
        foreach (var row in objects)
        {
            builder.Append(CultureInfo.InvariantCulture, $"object {row[0]} {row[1]} on {row[2]}: {CollapseWhitespace(row[3])}\n");
        }

        foreach (var table in objects.Where(row => row[0] == "table").Select(row => row[1]!))
        {
            foreach (var column in Query(connection, $"SELECT cid, name, type, \"notnull\", dflt_value, pk, hidden FROM pragma_table_xinfo('{table}') ORDER BY cid"))
            {
                builder.Append(CultureInfo.InvariantCulture, $"column {table}.{column[1]} #{column[0]} type={column[2]} notnull={column[3]} default={column[4] ?? "<none>"} pk={column[5]} hidden={column[6]}\n");
            }

            foreach (var index in Query(connection, $"SELECT name, \"unique\", origin, partial FROM pragma_index_list('{table}') ORDER BY name"))
            {
                var columns = Query(connection, $"SELECT seqno, cid, name, \"desc\", coll, key FROM pragma_index_xinfo('{index[0]}') ORDER BY seqno")
                    .Select(c => $"{c[2] ?? "<expr>"}(cid={c[1]},desc={c[3]},coll={c[4]},key={c[5]})");
                builder.Append(CultureInfo.InvariantCulture, $"index {table}.{index[0]} unique={index[1]} origin={index[2]} partial={index[3]} [{string.Join(", ", columns)}]\n");
            }

            foreach (var key in Query(connection, $"SELECT id, seq, \"table\", \"from\", \"to\", on_update, on_delete, match FROM pragma_foreign_key_list('{table}') ORDER BY id, seq"))
            {
                builder.Append(CultureInfo.InvariantCulture, $"foreign_key {table} #{key[0]}.{key[1]} {key[3]} -> {key[2]}.{key[4]} on_update={key[5]} on_delete={key[6]} match={key[7]}\n");
            }

            foreach (var values in Query(connection, $"SELECT * FROM \"{table}\" ORDER BY rowid"))
            {
                builder.Append(CultureInfo.InvariantCulture, $"row {table}: {string.Join(" | ", values.Select(MaskTimestamp))}\n");
            }
        }

        return builder.ToString();
    }

    /// <summary>Build a database by running a SQL script (the checked-in reference) with foreign keys off, as Alembic seeded it.</summary>
    public static void Execute(string databasePath, string sql)
    {
        using var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = databasePath, Pooling = false }.ToString());
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=OFF;\n" + sql;
        command.ExecuteNonQuery();
    }

    public static long ScalarLong(string databasePath, string sql)
    {
        using var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = databasePath, Pooling = false }.ToString());
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt64(command.ExecuteScalar(), CultureInfo.InvariantCulture);
    }

    private static List<string?[]> Query(SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        using var reader = command.ExecuteReader();
        var rows = new List<string?[]>();
        while (reader.Read())
        {
            var row = new string?[reader.FieldCount];
            for (var i = 0; i < reader.FieldCount; i++)
            {
                row[i] = reader.IsDBNull(i) ? null : Convert.ToString(reader.GetValue(i), CultureInfo.InvariantCulture);
            }

            rows.Add(row);
        }

        return rows;
    }

    private static string CollapseWhitespace(string? sql) => sql is null ? "<no sql>" : Whitespace().Replace(sql, " ").Trim();

    private static string MaskTimestamp(string? value) =>
        value is null ? "NULL" : SeedTimestamp().IsMatch(value) ? "<timestamp>" : value;

    [GeneratedRegex(@"\s+")]
    private static partial Regex Whitespace();

    [GeneratedRegex(@"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")]
    private static partial Regex SeedTimestamp();
}
