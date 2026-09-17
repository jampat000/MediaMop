using System.Text;

namespace Weir.Infrastructure.Auth;

/// <summary>
/// Reads the new password from the operator when <c>--password</c> was not given
/// (port of <c>getpass.getpass</c>'s two calls in <c>weir.platform.auth.recover._read_new_password</c>).
/// </summary>
public interface IRecoverPasswordPrompt
{
    /// <summary>Whether a password can be prompted for at all (Python's <c>sys.stdin.isatty()</c>).</summary>
    bool IsInteractive { get; }

    /// <summary>Read one line from the operator without echoing it.</summary>
    string ReadPassword(string prompt);
}

/// <summary>
/// The real console: no echo at all, not even the masking characters some prompts show, matching
/// <c>getpass.getpass</c>.
/// </summary>
public sealed class ConsoleRecoverPasswordPrompt : IRecoverPasswordPrompt
{
    public bool IsInteractive => !Console.IsInputRedirected;

    public string ReadPassword(string prompt)
    {
        ArgumentNullException.ThrowIfNull(prompt);
        Console.Write(prompt);
        var buffer = new StringBuilder();
        while (true)
        {
            var key = Console.ReadKey(intercept: true);
            if (key.Key == ConsoleKey.Enter)
            {
                Console.WriteLine();
                return buffer.ToString();
            }

            if (key.Key == ConsoleKey.Backspace)
            {
                if (buffer.Length > 0)
                {
                    buffer.Length--;
                }

                continue;
            }

            if (!char.IsControl(key.KeyChar))
            {
                buffer.Append(key.KeyChar);
            }
        }
    }
}
