using Microsoft.Extensions.Logging.Abstractions;
using Weir.Core.Auth;
using Weir.Core.Configuration;
using Weir.Core.Security;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Runtime;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Tests.Auth;

/// <summary>
/// A temporary <c>WEIR_HOME</c> with a database at head, for <see cref="RecoverCommand"/> tests. Mirrors
/// <c>Weir.Infrastructure.Tests.Platform.StoreFixture</c> but also keeps the <see cref="RuntimeEnvironment"/>
/// itself, since <see cref="RecoverCommand.RunAsync"/> loads options from it directly (as the real
/// <c>Weir recover</c> entry point does), rather than from an already-built <see cref="WeirOptions"/>.
/// </summary>
internal sealed class RecoverFixture : IDisposable
{
    public RecoverFixture()
    {
        Home = new TempDirectory();
        var variables = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["WEIR_HOME"] = Home.Path,
            ["WEIR_SESSION_SECRET"] = "recover-tests-session-secret-0123456789",
        };
        Runtime = new RuntimeEnvironment(variables, OperatingSystem.IsWindows(), Home.Path, Home.Path);
        Options = WeirOptionsLoader.Load(Runtime);
        RuntimeDirectories.Ensure(Options);
        Database = new SqliteDatabase(Options.DbPath);
        new SchemaMigrator(Database).EnsureAtHead();
        Auth = new AuthService(Options, TimeProvider.System, Database, NullLoggerFactory.Instance);
    }

    public TempDirectory Home { get; }

    public RuntimeEnvironment Runtime { get; }

    public WeirOptions Options { get; }

    public SqliteDatabase Database { get; }

    public AuthService Auth { get; }

    /// <summary>Inserts a user and, optionally, some active sessions for it (via a real login).</summary>
    public async Task<UserRecord> SeedUserAsync(string username, string password, bool active = true, string role = "admin", int sessions = 0)
    {
        var uow = await UnitOfWork.OpenAsync(Database);
        await using (uow.ConfigureAwait(false))
        {
            var id = await AuthStore.InsertUserAsync(uow, username, PasswordHasher.Hash(password), role, active).ConfigureAwait(false);
            await uow.CommitAsync().ConfigureAwait(false);
            var user = new UserRecord(id, username, PasswordHasher.Hash(password), role, active);
            for (var i = 0; i < sessions; i++)
            {
                var loginUow = await UnitOfWork.OpenAsync(Database).ConfigureAwait(false);
                await using (loginUow.ConfigureAwait(false))
                {
                    await Auth.CreateSessionAsync(loginUow, user, false, "Browser session").ConfigureAwait(false);
                    await loginUow.CommitAsync().ConfigureAwait(false);
                }
            }

            return user;
        }
    }

    public async Task<T> WithUnitOfWork<T>(Func<UnitOfWork, Task<T>> work)
    {
        var uow = await UnitOfWork.OpenAsync(Database).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            return await work(uow).ConfigureAwait(false);
        }
    }

    public void Dispose()
    {
        Database.ClearPool();
        Home.Dispose();
    }
}

/// <summary>A scripted password prompt for the non-interactive/mismatch/normal prompt paths.</summary>
internal sealed class FakePasswordPrompt(bool isInteractive, params string[] answers) : IRecoverPasswordPrompt
{
    private int _index;

    public bool IsInteractive { get; } = isInteractive;

    public string ReadPassword(string prompt) => answers[_index++];
}

public sealed class RecoverCommandTests
{
    private const string OldPassword = "old-password-strong";
    private const string NewPassword = "brand-new-password-strong";

    private static (System.IO.StringWriter Out, System.IO.StringWriter Err) Writers() => (new(), new());

    [Fact]
    public async Task A_locked_out_inactive_admin_is_recovered_sessions_revoked_and_event_recorded()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword, active: false, sessions: 2);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--username", "james", "--password", NewPassword],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitOk, exit);
        Assert.Equal(string.Empty, stderr.ToString());
        Assert.Contains("Password reset for 'james'.", stdout.ToString());
        Assert.Contains("The account is active and has the admin role.", stdout.ToString());
        Assert.Contains("2 signed-in session(s) were ended — sign in again with the new password.", stdout.ToString());

        var user = await fixture.WithUnitOfWork(uow => AuthStore.FindUserByLowerUsernameAsync(uow, "james"));
        Assert.NotNull(user);
        Assert.True(user!.IsActive);
        Assert.Equal(PasswordVerification.Match, PasswordHasher.Verify(NewPassword, user.PasswordHash));
        Assert.Equal(PasswordVerification.Mismatch, PasswordHasher.Verify(OldPassword, user.PasswordHash));

        var activeSessions = await fixture.WithUnitOfWork(uow =>
            uow.CountAsync("SELECT count(*) FROM user_sessions WHERE user_id = $id AND revoked_at IS NULL", ("$id", user.Id)));
        Assert.Equal(0, activeSessions);
        var revokedSessions = await fixture.WithUnitOfWork(uow =>
            uow.CountAsync("SELECT count(*) FROM user_sessions WHERE user_id = $id AND revoked_at IS NOT NULL", ("$id", user.Id)));
        Assert.Equal(2, revokedSessions);

        var eventRows = await fixture.WithUnitOfWork(uow => uow.QueryAsync(
            "SELECT title, detail FROM activity_events WHERE event_type = 'auth.password_changed'",
            reader => (Title: SqliteValues.GetString(reader, 0), Detail: SqliteValues.GetString(reader, 1))));
        var eventRow = Assert.Single(eventRows);
        Assert.Equal("Password recovered from the server", eventRow.Title);
        Assert.Equal("james — reset from the server console. 2 signed-in session(s) were ended.", eventRow.Detail);
    }

    [Fact]
    public async Task Recovery_of_the_only_account_needs_no_username()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword, role: "operator");
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--password", NewPassword],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitOk, exit);
        Assert.Contains("Password reset for 'james'.", stdout.ToString());
        // Only an admin account gets the extra confirmation line.
        Assert.DoesNotContain("has the admin role", stdout.ToString());
    }

    [Fact]
    public async Task Refuses_with_no_accounts_and_points_at_setup()
    {
        using var fixture = new RecoverFixture();
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--password", NewPassword],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitFailed, exit);
        Assert.Contains("No accounts exist yet, so there is nothing to recover.", stderr.ToString());
        Assert.Contains("/setup", stderr.ToString());
    }

    [Fact]
    public async Task Refuses_an_unknown_username()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--username", "nobody", "--password", NewPassword],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitFailed, exit);
        Assert.Contains("No account named 'nobody'. Use --list to see them.", stderr.ToString());
    }

    [Fact]
    public async Task Several_accounts_without_username_asks_for_one()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword);
        await fixture.SeedUserAsync("alice", OldPassword);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--password", NewPassword],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitUsage, exit);
        Assert.Contains("Several accounts exist. Pass --username. Found: alice, james", stderr.ToString());
    }

    [Fact]
    public async Task A_weak_password_is_refused_and_nothing_changes()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--username", "james", "--password", "password"],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitFailed, exit);
        Assert.StartsWith("Could not reset the password:", stderr.ToString());

        var user = await fixture.WithUnitOfWork(uow => AuthStore.FindUserByLowerUsernameAsync(uow, "james"));
        Assert.Equal(PasswordVerification.Match, PasswordHasher.Verify(OldPassword, user!.PasswordHash));
    }

    [Fact]
    public async Task List_reports_accounts_and_changes_nothing()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword, active: false);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(["--list"], fixture.Runtime, stdout, stderr, new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitOk, exit);
        Assert.Contains("james", stdout.ToString());
        Assert.Contains("role=admin", stdout.ToString());
        Assert.Contains("INACTIVE", stdout.ToString());

        var user = await fixture.WithUnitOfWork(uow => AuthStore.FindUserByLowerUsernameAsync(uow, "james"));
        Assert.Equal(PasswordVerification.Match, PasswordHasher.Verify(OldPassword, user!.PasswordHash));
        Assert.False(user.IsActive);
    }

    [Fact]
    public async Task List_with_no_accounts_points_at_setup()
    {
        using var fixture = new RecoverFixture();
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(["--list"], fixture.Runtime, stdout, stderr, new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitOk, exit);
        Assert.Contains("No accounts. Open /setup to create the first one.", stdout.ToString());
    }

    [Fact]
    public async Task Without_password_or_a_terminal_the_operator_is_told_to_pass_one()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--username", "james"],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitFailed, exit);
        Assert.Contains(
            "Could not reset the password: No terminal available to prompt for a password. Pass --password instead.",
            stderr.ToString());
    }

    [Fact]
    public async Task A_prompted_mismatch_is_refused()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--username", "james"],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: true, NewPassword, "something-else-entirely"));

        Assert.Equal(RecoverCommand.ExitFailed, exit);
        Assert.Contains("Could not reset the password: The two passwords did not match.", stderr.ToString());
    }

    [Fact]
    public async Task A_matching_prompted_password_recovers_the_account()
    {
        using var fixture = new RecoverFixture();
        await fixture.SeedUserAsync("james", OldPassword);
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(
            ["--username", "james"],
            fixture.Runtime,
            stdout,
            stderr,
            new FakePasswordPrompt(isInteractive: true, NewPassword, NewPassword));

        Assert.Equal(RecoverCommand.ExitOk, exit);
        var user = await fixture.WithUnitOfWork(uow => AuthStore.FindUserByLowerUsernameAsync(uow, "james"));
        Assert.Equal(PasswordVerification.Match, PasswordHasher.Verify(NewPassword, user!.PasswordHash));
    }

    [Fact]
    public async Task Help_prints_usage_and_exits_ok()
    {
        using var fixture = new RecoverFixture();
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(["--help"], fixture.Runtime, stdout, stderr, new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitOk, exit);
        Assert.Contains("usage: Weir recover", stdout.ToString());
        Assert.Contains("--username", stdout.ToString());
        Assert.Contains("--list", stdout.ToString());
        Assert.Empty(stderr.ToString());
    }

    [Fact]
    public async Task An_unknown_flag_is_refused_like_argparse()
    {
        using var fixture = new RecoverFixture();
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(["--bogus"], fixture.Runtime, stdout, stderr, new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitFailed, exit);
        Assert.Contains("usage: Weir recover", stderr.ToString());
        Assert.Contains("unrecognized arguments: --bogus", stderr.ToString());
        Assert.Empty(stdout.ToString());
    }

    [Fact]
    public async Task A_username_flag_missing_its_value_is_refused()
    {
        using var fixture = new RecoverFixture();
        var (stdout, stderr) = Writers();

        var exit = await RecoverCommand.RunAsync(["--username"], fixture.Runtime, stdout, stderr, new FakePasswordPrompt(isInteractive: false));

        Assert.Equal(RecoverCommand.ExitFailed, exit);
        Assert.Contains("argument --username: expected one argument", stderr.ToString());
    }
}
