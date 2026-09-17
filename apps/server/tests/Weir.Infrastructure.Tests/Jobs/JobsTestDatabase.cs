using System.Globalization;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Activity;
using Weir.Core.Jobs;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Jobs;

/// <summary>A real SQLite file at the current schema in a temporary directory, with a job store over it.</summary>
internal sealed class JobsTestDatabase : IDisposable
{
    public static readonly DateTimeOffset T0 = new(2026, 4, 10, 12, 0, 0, TimeSpan.Zero);

    private readonly TempDirectory _directory = new();

    /// <param name="keepSeedRows">
    /// Keep the singleton settings and the two seeded libraries a fresh database has. The Python tests
    /// these port use <c>create_all</c>, which seeds nothing, so they are removed by default.
    /// </param>
    public JobsTestDatabase(bool keepSeedRows = false)
    {
        DbPath = _directory.Join("weir.sqlite3");
        Database = new SqliteDatabase(DbPath);
        new SchemaMigrator(Database).EnsureAtHead();
        if (!keepSeedRows)
        {
            Execute("DELETE FROM refiner_libraries; DELETE FROM suite_settings; DELETE FROM refiner_operator_settings;");
        }

        Clock = new SettableTimeProvider(T0);
        Store = new RefinerJobStore(Database, Clock);
    }

    public string DbPath { get; }

    public string Home => _directory.Path;

    public SqliteDatabase Database { get; }

    public SettableTimeProvider Clock { get; }

    public RefinerJobStore Store { get; }

    public string Join(params string[] parts) => _directory.Join(parts);

    public RefinerJobProcessor Processor(
        IEnumerable<IJobHandler>? handlers = null,
        IUnhandledJobFailureRecorder? recorder = null,
        IJobNotifications? notifications = null,
        bool claimAllKinds = false) =>
        new(
            Store,
            new JobHandlerRegistry(handlers ?? []),
            new SqliteActivityWriter(Database),
            recorder ?? new NoUnhandledJobFailureRecorder(),
            notifications ?? new NoJobNotifications(),
            Clock,
            NullLogger<RefinerJobProcessor>.Instance)
        {
            Kinds = claimAllKinds ? null : ClaimableKinds.For(new JobHandlerRegistry(handlers ?? [])),
        };

    public int Execute(string sql, params (string Name, object? Value)[] parameters)
    {
        using var connection = Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        }

        return command.ExecuteNonQuery();
    }

    public object? Scalar(string sql, params (string Name, object? Value)[] parameters)
    {
        using var connection = Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        foreach (var (name, value) in parameters)
        {
            command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        }

        return command.ExecuteScalar();
    }

    public long Count(string sql, params (string Name, object? Value)[] parameters) =>
        Convert.ToInt64(Scalar(sql, parameters), CultureInfo.InvariantCulture);

    public List<(string EventType, string Title, string? Detail, string? Result)> ActivityEvents()
    {
        using var connection = Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT event_type, title, detail, result FROM activity_events ORDER BY id";
        using var reader = command.ExecuteReader();
        var rows = new List<(string, string, string?, string?)>();
        while (reader.Read())
        {
            rows.Add((reader.GetString(0), reader.GetString(1), reader.IsDBNull(2) ? null : reader.GetString(2), reader.IsDBNull(3) ? null : reader.GetString(3)));
        }

        return rows;
    }

    /// <summary>Insert the suite settings singleton, as <c>SuiteSettingsRow(id=1, app_timezone="UTC")</c>.</summary>
    public void SeedSuiteSettings(string timezone = "UTC") =>
        Execute("INSERT INTO suite_settings (id, app_timezone) VALUES (1, @tz)", ("@tz", timezone));

    public void Pause(bool scanWhilePaused, DateTimeOffset? until = null) =>
        Execute(
            "UPDATE suite_settings SET processing_paused = 1, scan_while_paused = @scan, processing_paused_until = @until WHERE id = 1",
            ("@scan", scanWhilePaused ? 1 : 0),
            ("@until", until is { } value ? PythonTimestamps.Orm(value) : null));

    /// <summary>Insert a library row and return its id.</summary>
    public long AddLibrary(
        string name = "Movies",
        bool enabled = true,
        bool scheduleEnabled = true,
        string scheduleGrid = "",
        string mediaType = "movie",
        string workFolder = "",
        string outputFolder = "/srv/out",
        int maxConcurrentFiles = 1)
    {
        using var connection = Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText =
            "INSERT INTO refiner_libraries (name, enabled, media_type, watched_folder, work_folder, output_folder, schedule_enabled, schedule_grid, max_concurrent_files) " +
            "VALUES (@name, @enabled, @media_type, '/srv/in', @work, @output, @schedule_enabled, @grid, @max) RETURNING id";
        command.Parameters.AddWithValue("@name", name);
        command.Parameters.AddWithValue("@enabled", enabled ? 1 : 0);
        command.Parameters.AddWithValue("@media_type", mediaType);
        command.Parameters.AddWithValue("@work", workFolder);
        command.Parameters.AddWithValue("@output", outputFolder);
        command.Parameters.AddWithValue("@schedule_enabled", scheduleEnabled ? 1 : 0);
        command.Parameters.AddWithValue("@grid", scheduleGrid);
        command.Parameters.AddWithValue("@max", maxConcurrentFiles);
        return Convert.ToInt64(command.ExecuteScalar(), CultureInfo.InvariantCulture);
    }

    /// <summary>A raw row insert, bypassing the enqueue guard, as Python tests do with <c>session.add(RefinerJob(...))</c>.</summary>
    public void InsertRawJob(string dedupeKey, string jobKind, string status = RefinerJobStatus.Pending, string? leaseOwner = null,
        string? leaseExpiresAt = null, int attemptCount = 0, int maxAttempts = 3, string? payloadJson = null) =>
        Execute(
            "INSERT INTO refiner_jobs (dedupe_key, job_kind, status, lease_owner, lease_expires_at, attempt_count, max_attempts, payload_json) " +
            "VALUES (@d, @k, @s, @o, @e, @a, @m, @p)",
            ("@d", dedupeKey), ("@k", jobKind), ("@s", status), ("@o", leaseOwner), ("@e", leaseExpiresAt), ("@a", attemptCount), ("@m", maxAttempts), ("@p", payloadJson));

    public void Dispose()
    {
        Database.ClearPool();
        _directory.Dispose();
    }
}

/// <summary>A clock the test sets; timers still run in real time.</summary>
internal sealed class SettableTimeProvider(DateTimeOffset now) : TimeProvider
{
    public DateTimeOffset Now { get; set; } = now;

    public override DateTimeOffset GetUtcNow() => Now;
}

/// <summary>A handler built from a delegate.</summary>
internal sealed class DelegateHandler(string jobKind, Func<JobWorkContext, Task> run) : IJobHandler
{
    public DelegateHandler(string jobKind, Action<JobWorkContext> run)
        : this(jobKind, context =>
        {
            run(context);
            return Task.CompletedTask;
        })
    {
    }

    public string JobKind => jobKind;

    public Task HandleAsync(JobWorkContext context, CancellationToken cancellationToken) => run(context);
}

/// <summary>Collects Activity drafts instead of writing them.</summary>
internal sealed class RecordingActivityWriter : IActivityWriter
{
    public List<ActivityEventDraft> Events { get; } = [];

    public Task<long> RecordAsync(ActivityEventDraft draft, CancellationToken cancellationToken = default)
    {
        lock (Events)
        {
            Events.Add(draft);
            return Task.FromResult((long)Events.Count);
        }
    }
}
