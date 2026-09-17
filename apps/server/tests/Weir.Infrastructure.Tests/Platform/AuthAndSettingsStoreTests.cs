using System.Text;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Auth;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Security;
using Weir.Core.Time;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Logging;
using Weir.Infrastructure.Runtime;
using Weir.Infrastructure.Settings;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Platform;

/// <summary>A temporary WEIR_HOME with a database at head, the options for it and a clock the test moves.</summary>
internal sealed class StoreFixture : IDisposable
{
    public StoreFixture(params (string Name, string Value)[] variables)
    {
        Home = new TempDirectory();
        var dictionary = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["WEIR_HOME"] = Home.Path,
            ["WEIR_SESSION_SECRET"] = "store-tests-session-secret-0123456789",
        };
        foreach (var (name, value) in variables)
        {
            dictionary[name] = value;
        }

        Options = WeirOptionsLoader.Load(new RuntimeEnvironment(dictionary, OperatingSystem.IsWindows(), Home.Path, Home.Path));
        RuntimeDirectories.Ensure(Options);
        Database = new SqliteDatabase(Options.DbPath);
        new SchemaMigrator(Database).EnsureAtHead();
        Clock = new MovableClock(new DateTimeOffset(2026, 1, 15, 10, 0, 0, TimeSpan.Zero));
        Auth = new AuthService(Options, Clock, Database, NullLoggerFactory.Instance);
    }

    public TempDirectory Home { get; }

    public WeirOptions Options { get; }

    public SqliteDatabase Database { get; }

    public MovableClock Clock { get; }

    public AuthService Auth { get; }

    public async Task<T> WithUnitOfWork<T>(Func<UnitOfWork, Task<T>> work, bool commit = true)
    {
        var uow = await UnitOfWork.OpenAsync(Database);
        await using (uow)
        {
            var result = await work(uow);
            if (commit)
            {
                await uow.CommitAsync();
            }

            return result;
        }
    }

    public async Task<long> Scalar(string sql)
    {
        using var connection = Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        return Convert.ToInt64(await command.ExecuteScalarAsync(), System.Globalization.CultureInfo.InvariantCulture);
    }

    public async Task Execute(string sql)
    {
        using var connection = Database.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        await command.ExecuteNonQueryAsync();
    }

    public void Dispose() => Home.Dispose();
}

internal sealed class MovableClock(DateTimeOffset start) : TimeProvider
{
    private DateTimeOffset _now = start;

    public override DateTimeOffset GetUtcNow() => _now;

    public void Set(DateTimeOffset now) => _now = now;
}

public sealed class AuthAndSettingsStoreTests
{
    private const string Password = "test-password-strong";

    [Fact]
    public async Task Login_keeps_only_the_newest_five_active_sessions()
    {
        using var fixture = new StoreFixture();
        await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", PasswordHasher.Hash(Password), "admin", true));
        for (var i = 0; i < 6; i++)
        {
            fixture.Clock.Set(fixture.Clock.GetUtcNow().AddSeconds(1));
            var login = await fixture.WithUnitOfWork(uow => fixture.Auth.LoginAsync(uow, "ALICE", Password, false, "Browser session"));
            Assert.NotNull(login);
        }

        Assert.Equal(5, await fixture.Scalar("SELECT count(*) FROM user_sessions WHERE revoked_at IS NULL"));
        Assert.Equal(1, await fixture.Scalar("SELECT count(*) FROM user_sessions WHERE revoked_at IS NOT NULL"));
    }

    [Fact]
    public async Task The_session_cap_ignores_sessions_past_their_absolute_expiry()
    {
        using var fixture = new StoreFixture();
        var userId = await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", "x", "admin", true));
        var user = new UserRecord(userId, "alice", "x", "admin", true);
        for (var i = 0; i < 5; i++)
        {
            await fixture.WithUnitOfWork(async uow =>
            {
                var (row, _) = await fixture.Auth.CreateSessionAsync(uow, user, false, "Browser session");
                await uow.ExecuteAsync("UPDATE user_sessions SET absolute_expires_at = $at WHERE id = $id", ("$at", "2026-01-15 09:59:59.000000"), ("$id", row.Id));
                return row;
            });
        }

        await fixture.WithUnitOfWork(uow => fixture.Auth.CreateSessionAsync(uow, user, false, "Browser session"));
        Assert.Equal(0, await fixture.Scalar("SELECT count(*) FROM user_sessions WHERE revoked_at IS NOT NULL"));
    }

    [Fact]
    public async Task Last_seen_is_persisted_at_most_once_a_minute()
    {
        using var fixture = new StoreFixture(("WEIR_SESSION_IDLE_MINUTES", "720"));
        var userId = await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", "x", "admin", true));
        var (_, raw) = await fixture.WithUnitOfWork(uow => fixture.Auth.CreateSessionAsync(uow, new UserRecord(userId, "alice", "x", "admin", true), false, "b"));

        fixture.Clock.Set(fixture.Clock.GetUtcNow().AddSeconds(30));
        Assert.NotNull(await fixture.WithUnitOfWork(uow => fixture.Auth.LoadValidSessionAsync(uow, raw)));
        Assert.Equal(1, await fixture.Scalar("SELECT count(*) FROM user_sessions WHERE last_seen_at = '2026-01-15 10:00:00.000000'"));

        fixture.Clock.Set(new DateTimeOffset(2026, 1, 15, 10, 1, 1, TimeSpan.Zero));
        var touched = await fixture.WithUnitOfWork(uow => fixture.Auth.LoadValidSessionAsync(uow, raw));
        Assert.True(touched!.Session.LastSeenAt.IsAware);
        Assert.Equal(1, await fixture.Scalar("SELECT count(*) FROM user_sessions WHERE last_seen_at = '2026-01-15 10:01:01.000000'"));
    }

    [Fact]
    public async Task An_expired_session_is_revoked_even_when_the_request_rolls_back()
    {
        // Deliberate fix (#529): Python's revoke is lost with the request's rollback.
        using var fixture = new StoreFixture();
        var userId = await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", "x", "admin", true));
        var (_, raw) = await fixture.WithUnitOfWork(uow => fixture.Auth.CreateSessionAsync(uow, new UserRecord(userId, "alice", "x", "admin", true), false, "b"));

        fixture.Clock.Set(fixture.Clock.GetUtcNow().AddDays(fixture.Options.SessionAbsoluteDays + 1));
        Assert.Null(await fixture.WithUnitOfWork(uow => fixture.Auth.LoadValidSessionAsync(uow, raw), commit: false));
        Assert.Equal(1, await fixture.Scalar("SELECT count(*) FROM user_sessions WHERE revoked_at IS NOT NULL"));
    }

    [Fact]
    public async Task Cleanup_deletes_revoked_and_expired_sessions()
    {
        using var fixture = new StoreFixture(("WEIR_SESSION_IDLE_MINUTES", "720"));
        var userId = await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", "x", "admin", true));
        var user = new UserRecord(userId, "alice", "x", "admin", true);
        var (revoked, _) = await fixture.WithUnitOfWork(uow => fixture.Auth.CreateSessionAsync(uow, user, false, "b"));
        var (expired, _) = await fixture.WithUnitOfWork(uow => fixture.Auth.CreateSessionAsync(uow, user, false, "b"));
        var (active, _) = await fixture.WithUnitOfWork(uow => fixture.Auth.CreateSessionAsync(uow, user, false, "b"));
        await fixture.Execute($"UPDATE user_sessions SET revoked_at = '2026-01-15 10:00:00.000000' WHERE id = '{revoked.Id}'");
        await fixture.Execute($"UPDATE user_sessions SET absolute_expires_at = '2026-01-15 09:59:59.000000' WHERE id = '{expired.Id}'");

        Assert.Equal(2, await fixture.WithUnitOfWork(uow => fixture.Auth.CleanupInactiveSessionsAsync(uow)));
        Assert.Equal(1, await fixture.Scalar($"SELECT count(*) FROM user_sessions WHERE id = '{active.Id}'"));
        Assert.Equal(1, await fixture.Scalar("SELECT count(*) FROM user_sessions"));
    }

    [Fact]
    public async Task An_inactive_sole_admin_reopens_bootstrap_and_recovery_leaves_exactly_one_admin()
    {
        using var fixture = new StoreFixture();
        await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", "argon2-placeholder", "admin", true));
        Assert.False(await fixture.WithUnitOfWork(AuthService.BootstrapAllowedAsync));
        await fixture.Execute("UPDATE users SET is_active = 0");
        Assert.True(await fixture.WithUnitOfWork(AuthService.BootstrapAllowedAsync));

        var created = await fixture.WithUnitOfWork(uow => AuthService.CreateInitialAdminAsync(uow, "alice-again", "recovered-password-strong"));
        Assert.True(created.IsActive);
        Assert.Equal(1, await fixture.Scalar("SELECT count(*) FROM users WHERE role = 'admin'"));
        Assert.False(await fixture.WithUnitOfWork(AuthService.BootstrapAllowedAsync));
    }

    [Fact]
    public async Task Username_and_password_changes_follow_the_python_rules()
    {
        using var fixture = new StoreFixture();
        var id = await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", PasswordHasher.Hash(Password), "admin", true));
        await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "bob", "x", "viewer", true));

        async Task<string> Error(Func<UnitOfWork, Task> work) =>
            (await Assert.ThrowsAsync<PyValueErrorException>(() => fixture.WithUnitOfWork(async uow => { await work(uow); return 0; }))).Message;

        Assert.Equal("Current password is incorrect.", await Error(uow => fixture.Auth.ChangeUsernameAsync(uow, id, "wrong", "james")));
        Assert.Equal("Username is required.", await Error(uow => fixture.Auth.ChangeUsernameAsync(uow, id, Password, "  ")));
        Assert.Equal("New username must be different from the current username.", await Error(uow => fixture.Auth.ChangeUsernameAsync(uow, id, Password, "alice")));
        Assert.Equal("That username is already taken.", await Error(uow => fixture.Auth.ChangeUsernameAsync(uow, id, Password, "BOB")));
        Assert.Equal("Alice", await fixture.WithUnitOfWork(uow => fixture.Auth.ChangeUsernameAsync(uow, id, Password, "Alice")));
        Assert.Equal("New password must be different from the current password.", await Error(uow => fixture.Auth.ChangePasswordAsync(uow, id, Password, Password)));
        Assert.Equal("Password must use a wider mix of characters.", await Error(uow => fixture.Auth.ChangePasswordAsync(uow, id, Password, "aaaaaaaaaa")));
    }

    [Fact]
    public async Task A_configuration_snapshot_is_written_when_due_and_path_traversal_is_refused()
    {
        using var fixture = new StoreFixture();
        var zones = new IanaTimeZoneResolver();
        var backups = new ConfigurationBackups(fixture.Options, fixture.Clock, zones);
        await fixture.Execute("UPDATE suite_settings SET configuration_backup_enabled = 1, configuration_backup_interval_hours = 6");

        Assert.Equal(1, await backups.RunTickAsync(fixture.Database, new DateTime(2026, 1, 15, 10, 0, 0, DateTimeKind.Utc)));
        Assert.Equal(0, await backups.RunTickAsync(fixture.Database, new DateTime(2026, 1, 15, 12, 0, 0, DateTimeKind.Utc)));
        Assert.Equal(1, await fixture.Scalar("SELECT count(*) FROM suite_settings WHERE configuration_backup_last_run_at = '2026-01-15 10:00:00.000000'"));
        var file = Assert.Single(Directory.GetFiles(backups.Directory));
        var text = await File.ReadAllTextAsync(file);
        Assert.StartsWith("{\n  \"arr_library_operator_settings\": {", text, StringComparison.Ordinal);

        await fixture.Execute("INSERT INTO suite_configuration_backup (created_at, file_name, size_bytes) VALUES ('2026-01-01 00:00:00.000000', '../outside.json', 2)");
        var id = await fixture.Scalar("SELECT max(id) FROM suite_configuration_backup");
        var error = await Assert.ThrowsAsync<PyValueErrorException>(() => fixture.WithUnitOfWork(uow => backups.GetFileAsync(uow, id)));
        Assert.Equal("Configuration snapshot file name is invalid.", error.Message);
    }

    [Fact]
    public async Task Only_the_newest_five_snapshots_are_kept()
    {
        using var fixture = new StoreFixture();
        var backups = new ConfigurationBackups(fixture.Options, fixture.Clock, new IanaTimeZoneResolver());
        for (var i = 0; i < 7; i++)
        {
            fixture.Clock.Set(fixture.Clock.GetUtcNow().AddMinutes(1));
            await fixture.WithUnitOfWork(backups.CreateAsync);
        }

        Assert.Equal(5, await fixture.Scalar("SELECT count(*) FROM suite_configuration_backup"));
        Assert.Equal(5, Directory.GetFiles(backups.Directory).Length);
    }

    [Fact]
    public void Update_settings_files_round_trip_and_fall_back_to_notify_only()
    {
        using var fixture = new StoreFixture();
        var files = new UpdateFiles(fixture.Options);
        Assert.Equal("{\"mode\":\"Auto\",\"check_on_startup\":true,\"check_interval_minutes\":60}", PyJsonWriter.Dumps(files.ReadSettings(), PyJsonFormat.Response));
        var foreign = Path.Join(fixture.Home.Path, "update-settings.json.tmp");
        File.WriteAllText(foreign, "{\"mode\": \"Auto\"}");
        files.WriteSettings("DownloadOnly", false, 240);
        Assert.Equal("{\"mode\":\"DownloadOnly\",\"check_on_startup\":false,\"check_interval_minutes\":240}", PyJsonWriter.Dumps(files.ReadSettings(), PyJsonFormat.Response));
        Assert.True(File.Exists(foreign));
        Assert.Empty(Directory.GetFiles(fixture.Home.Path, ".update-settings.json.*.tmp"));
        File.WriteAllText(Path.Join(fixture.Home.Path, "update-settings.json"), "{\"mode\": \"Notify");
        var warned = new List<string>();
        Assert.Equal("NotifyOnly", ((PyStr)files.ReadSettings(warned.Add)["mode"]).Value);
        Assert.Single(warned);

        Assert.Equal("{\"downloaded\":false,\"pending_version\":null}", PyJsonWriter.Dumps(files.ReadState(), PyJsonFormat.Response));
        File.WriteAllText(Path.Join(fixture.Home.Path, "update-state.json"), "{\"downloaded\": true, \"version\": \"2.0.0\"}");
        Assert.Equal("{\"downloaded\":true,\"pending_version\":\"2.0.0\"}", PyJsonWriter.Dumps(files.ReadState(), PyJsonFormat.Response));
        files.WriteApplyFlag();
        Assert.True(File.Exists(Path.Join(fixture.Home.Path, "update-apply-now")));
    }

    [Fact]
    public void Log_lines_with_invalid_utf8_are_read_with_replacement_characters()
    {
        // Deliberate fix (#536): Python's reader fails the request on one bad byte.
        using var directory = new TempDirectory();
        var path = directory.Join("weir.log");
        File.WriteAllBytes(path, [.. Encoding.UTF8.GetBytes("{\"timestamp\":\"2099-01-01T00:00:00Z\",\"level\":\"INFO\",\"logger\":\"weir.x\",\"message\":\"bad "), 0xFF, .. "\"}\n"u8]);
        using var log = new WeirLogFile(path, TimeProvider.System);
        log.WriteLine("{\"timestamp\":\"2099-01-01T00:00:01Z\",\"level\":\"INFO\",\"logger\":\"weir.x\",\"message\":\"good\"}");
        var lines = new List<string>();
        Assert.True(log.ReadLines(lines.Add));
        Assert.Equal(2, lines.Count);
        Assert.Contains("bad �", lines[0], StringComparison.Ordinal);
        Assert.True(log.Prune(3650));
    }

    [Fact]
    public async Task The_log_file_appends_after_content_written_by_someone_else()
    {
        using var directory = new TempDirectory();
        var path = directory.Join("weir.log");
        using var log = new WeirLogFile(path, TimeProvider.System);
        log.WriteLine("first");
        await using (var other = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete))
        {
            await other.WriteAsync("second\n"u8.ToArray());
        }

        log.WriteLine("third");
        var lines = new List<string>();
        log.ReadLines(lines.Add);
        Assert.Equal(["first", "second", "third"], lines);
    }

    [Fact]
    public void Time_zones_resolve_iana_names_on_every_platform()
    {
        var zones = new IanaTimeZoneResolver();
        Assert.True(zones.TryFind("Europe/London", out _));
        Assert.True(zones.TryFind("UTC", out _));
        Assert.False(zones.TryFind("Not/A_Real_Zone", out _));
    }

    [Fact]
    public async Task Sqlite_constraint_errors_are_recognised()
    {
        using var fixture = new StoreFixture();
        await fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "alice", "x", "admin", true));
        var error = await Assert.ThrowsAsync<SqliteException>(() => fixture.WithUnitOfWork(uow => AuthStore.InsertUserAsync(uow, "ALICE", "x", "admin", true)));
        Assert.True(SqliteValues.IsIntegrityError(error));
    }

    [Fact]
    public void Sqlite_datetimes_use_sqlalchemy_storage_and_pydantic_output()
    {
        var value = PyDateTime.FromUtc(new DateTime(2026, 9, 17, 2, 19, 51, DateTimeKind.Utc).AddTicks(2553240));
        Assert.Equal("2026-09-17 02:19:51.255324", value.ToSqlite());
        Assert.True(PyDateTime.TryFromIsoFormat(value.ToSqlite(), out var read));
        Assert.Equal("2026-09-17T02:19:51.255324", read.PydanticJson());
        Assert.Equal("2026-09-17T02:19:51.255324Z", value.PydanticJson());
        Assert.Equal("2026-09-17T02:19:51.255324+00:00", value.IsoFormat());
        Assert.True(PyDateTime.TryFromIsoFormat("2026-09-17 02:19:51", out var whole));
        Assert.Equal("2026-09-17T02:19:51", whole.PydanticJson());
    }
}
