using System.Globalization;
using System.Numerics;

namespace Weir.Core.Configuration;

/// <summary>
/// The few Python standard-library behaviours that <c>weir.core.config</c> leans on, reproduced
/// so the same environment produces the same settings: <c>int()</c> parsing,
/// <c>urllib.parse.urlparse</c> host/port splitting and <c>pathlib</c> path resolution.
/// </summary>
internal static class PythonCompat
{
    /// <summary>
    /// <c>int(raw)</c> for an already-stripped string: optional sign, ASCII digits, single
    /// underscores between digits. Values beyond <see cref="long"/> saturate.
    /// </summary>
    public static bool TryParseInt(string raw, out long value)
    {
        value = 0;
        var span = raw.AsSpan();
        var negative = false;
        if (span.Length > 0 && (span[0] == '+' || span[0] == '-'))
        {
            negative = span[0] == '-';
            span = span[1..];
        }

        if (span.Length == 0 || span[0] == '_' || span[^1] == '_')
        {
            return false;
        }

        var digits = new System.Text.StringBuilder(span.Length);
        var previousUnderscore = false;
        foreach (var c in span)
        {
            if (c == '_')
            {
                if (previousUnderscore)
                {
                    return false;
                }

                previousUnderscore = true;
                continue;
            }

            if (c is < '0' or > '9')
            {
                return false;
            }

            previousUnderscore = false;
            digits.Append(c);
        }

        var big = BigInteger.Parse(digits.ToString(), NumberStyles.None, CultureInfo.InvariantCulture);
        if (negative)
        {
            big = -big;
        }

        value = big > long.MaxValue ? long.MaxValue : big < long.MinValue ? long.MinValue : (long)big;
        return true;
    }

    /// <summary>The parts of <c>urlparse(raw)</c> that the loopback-origin expansion reads.</summary>
    public sealed record ParsedUrl(string Scheme, string? Hostname, int? Port);

    /// <summary>
    /// <c>urlparse(raw)</c> reduced to scheme, lower-cased hostname and port. Like Python, reading
    /// an invalid port raises, which fails startup.
    /// </summary>
    public static ParsedUrl ParseUrl(string raw)
    {
        var rest = raw;
        var scheme = string.Empty;
        var colon = rest.IndexOf(':', StringComparison.Ordinal);
        if (colon > 0 && IsSchemeText(rest[..colon]))
        {
            scheme = rest[..colon].ToLowerInvariant();
            rest = rest[(colon + 1)..];
        }

        if (!rest.StartsWith("//", StringComparison.Ordinal))
        {
            return new ParsedUrl(scheme, null, null);
        }

        rest = rest[2..];
        var end = rest.IndexOfAny(['/', '?', '#']);
        var netloc = end < 0 ? rest : rest[..end];
        var hostinfo = netloc[(netloc.LastIndexOf('@') + 1)..];

        string hostname;
        string port;
        if (hostinfo.Contains('[', StringComparison.Ordinal))
        {
            var afterBracket = hostinfo[(hostinfo.IndexOf('[', StringComparison.Ordinal) + 1)..];
            var close = afterBracket.IndexOf(']', StringComparison.Ordinal);
            hostname = close < 0 ? afterBracket : afterBracket[..close];
            var tail = close < 0 ? string.Empty : afterBracket[(close + 1)..];
            port = tail.StartsWith(':') ? tail[1..] : string.Empty;
        }
        else
        {
            var portColon = hostinfo.IndexOf(':', StringComparison.Ordinal);
            hostname = portColon < 0 ? hostinfo : hostinfo[..portColon];
            port = portColon < 0 ? string.Empty : hostinfo[(portColon + 1)..];
        }

        int? parsedPort = null;
        if (port.Length > 0)
        {
            if (!port.All(char.IsAsciiDigit))
            {
                throw new WeirConfigurationException($"Port could not be cast to integer value as '{port}'");
            }

            var number = BigInteger.Parse(port, NumberStyles.None, CultureInfo.InvariantCulture);
            if (number > 65535)
            {
                throw new WeirConfigurationException("Port out of range 0-65535");
            }

            parsedPort = (int)number;
        }

        return new ParsedUrl(scheme, hostname.Length == 0 ? null : hostname.ToLowerInvariant(), parsedPort);
    }

    private static bool IsSchemeText(string candidate) =>
        char.IsAsciiLetter(candidate[0]) &&
        candidate.All(c => char.IsAsciiLetterOrDigit(c) || c is '+' or '-' or '.');

    /// <summary><c>Path(raw).expanduser()</c> for the <c>~</c> and <c>~/…</c> forms.</summary>
    public static string ExpandUser(string path, RuntimeEnvironment runtime)
    {
        if (path == "~")
        {
            return runtime.UserHomeDirectory;
        }

        if (path.StartsWith("~/", StringComparison.Ordinal) ||
            (runtime.IsWindows && path.StartsWith("~\\", StringComparison.Ordinal)))
        {
            return Path.Join(runtime.UserHomeDirectory, path[2..]);
        }

        return path;
    }

    /// <summary><c>path.resolve()</c>: absolute against the working directory, normalized, no trailing separator.</summary>
    public static string Resolve(string path, RuntimeEnvironment runtime) =>
        Path.TrimEndingDirectorySeparator(Path.GetFullPath(path, runtime.CurrentDirectory));

    /// <summary>
    /// <c>str(Path(raw))</c>: <c>pathlib</c>'s lexical normalization without resolving
    /// (separators unified, duplicate separators and <c>.</c> segments dropped, no trailing separator).
    /// </summary>
    public static string NormalizeLexically(string path, RuntimeEnvironment runtime)
    {
        if (path.Length == 0)
        {
            return ".";
        }

        var separator = runtime.IsWindows ? '\\' : '/';
        var unified = runtime.IsWindows ? path.Replace('/', '\\') : path;
        var prefix = string.Empty;
        if (unified.StartsWith(new string(separator, 2), StringComparison.Ordinal) &&
            (unified.Length == 2 || unified[2] != separator))
        {
            prefix = new string(separator, 2);
        }
        else if (unified.StartsWith(separator))
        {
            prefix = separator.ToString();
        }

        var segments = unified[prefix.Length..]
            .Split(separator)
            .Where(segment => segment.Length > 0 && segment != ".");
        var joined = prefix + string.Join(separator, segments);
        return joined.Length == 0 ? "." : joined;
    }
}
