namespace Weir.Infrastructure.Auth;

/// <summary>
/// Parses <c>Weir recover</c>'s command line, the same three options the Python
/// <c>argparse.ArgumentParser</c> in <c>weir.platform.auth.recover.main</c> declared
/// (<c>--username</c>, <c>--password</c>, <c>--list</c>) plus the implicit <c>-h</c>/<c>--help</c>.
/// </summary>
public sealed record RecoverArguments(string? Username, string? Password, bool List, bool ShowHelp, string? Error)
{
    public const string UsageLine = "usage: Weir recover [-h] [--username USERNAME] [--password PASSWORD] [--list]";

    public static readonly string HelpText = UsageLine + "\n\n" +
        "Reset the Weir operator password from the server.\n\n" +
        "options:\n" +
        "  -h, --help            show this help message and exit\n" +
        "  --username USERNAME   Account to reset. Optional while there is only one.\n" +
        "  --password PASSWORD   New password. Omit to be prompted, which keeps it out\n" +
        "                        of your shell history.\n" +
        "  --list                List accounts and exit.\n";

    public static RecoverArguments Parse(IReadOnlyList<string> args)
    {
        ArgumentNullException.ThrowIfNull(args);
        string? username = null;
        string? password = null;
        var list = false;
        var unrecognized = new List<string>();

        for (var i = 0; i < args.Count; i++)
        {
            var arg = args[i];
            if (arg is "-h" or "--help")
            {
                return new RecoverArguments(null, null, false, true, null);
            }

            if (TryMatchOption(args, ref i, arg, "--username", out var usernameValue, out var missingValue))
            {
                if (missingValue)
                {
                    return Failure("argument --username: expected one argument");
                }

                username = usernameValue;
                continue;
            }

            if (TryMatchOption(args, ref i, arg, "--password", out var passwordValue, out missingValue))
            {
                if (missingValue)
                {
                    return Failure("argument --password: expected one argument");
                }

                password = passwordValue;
                continue;
            }

            if (arg == "--list")
            {
                list = true;
                continue;
            }

            unrecognized.Add(arg);
        }

        return unrecognized.Count > 0
            ? Failure($"unrecognized arguments: {string.Join(' ', unrecognized)}")
            : new RecoverArguments(username, password, list, false, null);
    }

    private static RecoverArguments Failure(string message) => new(null, null, false, false, message);

    /// <summary>Matches <paramref name="name"/> as <c>--name value</c> or <c>--name=value</c>, argparse-style.</summary>
    private static bool TryMatchOption(
        IReadOnlyList<string> args, ref int i, string arg, string name, out string? value, out bool missingValue)
    {
        value = null;
        missingValue = false;
        var prefix = name + "=";
        if (arg.StartsWith(prefix, StringComparison.Ordinal))
        {
            value = arg[prefix.Length..];
            return true;
        }

        if (arg != name)
        {
            return false;
        }

        if (i + 1 >= args.Count)
        {
            missingValue = true;
            return true;
        }

        i++;
        value = args[i];
        return true;
    }
}
