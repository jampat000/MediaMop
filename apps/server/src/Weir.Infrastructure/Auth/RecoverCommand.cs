using Weir.Core.Activity;
using Weir.Core.Auth;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Security;
using Weir.Core.Time;
using Weir.Infrastructure.Activity;
using Weir.Infrastructure.Runtime;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Auth;

/// <summary>
/// Port of <c>weir.platform.auth.recover</c> (#454, #553): recover the Weir operator account from the
/// server's own console when every session is locked out or the password is forgotten. Local-only —
/// there is no HTTP endpoint for this, exactly as Python shipped it as a console script rather than a
/// route. Reaching the server's own shell (and so its database, under <c>WEIR_HOME</c>) is the proof of
/// identity; there is no email reset and no second admin to rescue the first.
/// </summary>
public static class RecoverCommand
{
    public const int ExitOk = 0;

    /// <summary>Several accounts exist and no <c>--username</c> was given to choose one.</summary>
    public const int ExitUsage = 1;

    /// <summary>Nothing to recover, an unknown account, a rejected password, or a bad command line.</summary>
    public const int ExitFailed = 2;

    /// <summary>
    /// Runs <c>Weir recover</c>. <paramref name="args"/> excludes the leading <c>recover</c> word itself.
    /// </summary>
    public static async Task<int> RunAsync(
        IReadOnlyList<string> args,
        RuntimeEnvironment runtime,
        TextWriter stdout,
        TextWriter stderr,
        IRecoverPasswordPrompt passwordPrompt,
        TimeProvider? time = null)
    {
        ArgumentNullException.ThrowIfNull(args);
        ArgumentNullException.ThrowIfNull(runtime);
        ArgumentNullException.ThrowIfNull(stdout);
        ArgumentNullException.ThrowIfNull(stderr);
        ArgumentNullException.ThrowIfNull(passwordPrompt);

        var parsed = RecoverArguments.Parse(args);
        if (parsed.ShowHelp)
        {
            stdout.Write(RecoverArguments.HelpText);
            return ExitOk;
        }

        if (parsed.Error is { } parseError)
        {
            stderr.WriteLine(RecoverArguments.UsageLine);
            stderr.WriteLine($"Weir recover: error: {parseError}");
            return ExitFailed;
        }

        // WeirSettings.load() itself ensures the runtime directories and asserts the db path is usable;
        // WeirOptionsLoader.Load does not, so both calls are repeated here to match.
        var options = WeirOptionsLoader.Load(runtime);
        RuntimeDirectories.Ensure(options);
        RuntimeDirectories.AssertSqliteDbLocationUsable(options.DbPath);

        var database = new SqliteDatabase(options.DbPath);
        var uow = await UnitOfWork.OpenAsync(database).ConfigureAwait(false);
        await using (uow.ConfigureAwait(false))
        {
            var accounts = await AuthStore.ListUsersByUsernameAsync(uow).ConfigureAwait(false);

            if (parsed.List)
            {
                if (accounts.Count == 0)
                {
                    stdout.WriteLine("No accounts. Open /setup to create the first one.");
                    return ExitOk;
                }

                stdout.WriteLine($"Accounts in {options.DbPath}:");
                foreach (var row in accounts)
                {
                    stdout.WriteLine($"  {row.Username}  role={row.Role}  {(row.IsActive ? "active" : "INACTIVE")}");
                }

                return ExitOk;
            }

            if (accounts.Count == 0)
            {
                stderr.WriteLine("No accounts exist yet, so there is nothing to recover.");
                stderr.WriteLine("Open /setup in a browser to create the operator account.");
                return ExitFailed;
            }

            if (parsed.Username is null && accounts.Count > 1)
            {
                var names = string.Join(", ", accounts.Select(row => row.Username));
                stderr.WriteLine($"Several accounts exist. Pass --username. Found: {names}");
                return ExitUsage;
            }

            var user = await AuthStore.FindAccountForRecoveryAsync(uow, parsed.Username).ConfigureAwait(false);
            if (user is null)
            {
                stderr.WriteLine($"No account named {PyStrings.Repr(parsed.Username ?? string.Empty)}. Use --list to see them.");
                return ExitFailed;
            }

            int revoked;
            try
            {
                var newPassword = ReadNewPassword(parsed.Password, passwordPrompt);
                revoked = await ResetAccountPasswordAsync(uow, user, newPassword, time ?? TimeProvider.System).ConfigureAwait(false);
            }
            catch (PyValueErrorException exception)
            {
                // Strength and mismatch failures are the operator's to fix, not a crash.
                stderr.WriteLine($"Could not reset the password: {exception.Message}");
                return ExitFailed;
            }

            await uow.CommitAsync().ConfigureAwait(false);

            stdout.WriteLine($"Password reset for {PyStrings.Repr(user.Username)}.");
            if (user.Role == UserRoles.Admin)
            {
                stdout.WriteLine("The account is active and has the admin role.");
            }

            stdout.WriteLine($"{revoked} signed-in session(s) were ended — sign in again with the new password.");
            return ExitOk;
        }
    }

    /// <summary>
    /// Port of <c>reset_account_password</c>: validate the new password, re-activate the account (an
    /// inactive sole admin is its own lockout), revoke every still-active session and record it in
    /// Activity. Returns the number of sessions revoked.
    /// </summary>
    public static async Task<int> ResetAccountPasswordAsync(UnitOfWork uow, UserRecord user, string newPassword, TimeProvider time)
    {
        ArgumentNullException.ThrowIfNull(uow);
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(time);

        if (PasswordPolicy.Validate(newPassword, user.Username) is { } problem)
        {
            throw new PyValueErrorException(problem);
        }

        await AuthStore.UpdatePasswordHashAsync(uow, user.Id, PasswordHasher.Hash(newPassword)).ConfigureAwait(false);
        // An inactive account cannot sign in, so recovery that left this alone would "succeed" and
        // still leave the operator locked out.
        await AuthStore.SetActiveAsync(uow, user.Id, true).ConfigureAwait(false);

        var now = PyDateTime.UtcNow(time);
        var revoked = await AuthStore.RevokeActiveSessionsForUserAsync(uow, user.Id, now).ConfigureAwait(false);

        await ActivityStore.RecordAsync(
            uow,
            ActivityEventTypes.AuthPasswordChanged,
            "auth",
            "Password recovered from the server",
            $"{user.Username} — reset from the server console. {revoked} signed-in session(s) were ended.").ConfigureAwait(false);

        return revoked;
    }

    /// <summary>Port of <c>_read_new_password</c>.</summary>
    private static string ReadNewPassword(string? supplied, IRecoverPasswordPrompt prompt)
    {
        if (supplied is not null)
        {
            return supplied;
        }

        if (!prompt.IsInteractive)
        {
            throw new PyValueErrorException("No terminal available to prompt for a password. Pass --password instead.");
        }

        var first = prompt.ReadPassword("New password: ");
        var second = prompt.ReadPassword("Repeat new password: ");
        if (first != second)
        {
            throw new PyValueErrorException("The two passwords did not match.");
        }

        return first;
    }
}
