using System.Globalization;

namespace Weir.Core.Configuration;

/// <summary>
/// Where the HTTP server listens. The Python backend has no settings for this; its launchers pass
/// it in, and this keeps each launcher's contract:
/// <list type="bullet">
/// <item>the Windows tray starts the server with <c>--port &lt;port&gt;</c>;</item>
/// <item>the Docker entrypoint reads <c>PORT</c>;</item>
/// <item>both bind every interface, on port 8788 by default.</item>
/// </list>
/// <c>--host</c> narrows the bind address (local development uses 127.0.0.1).
/// </summary>
public sealed record ServerListenOptions(string Host, int Port)
{
    public const int DefaultPort = 8788;
    public const string DefaultHost = "0.0.0.0";

    public static ServerListenOptions Parse(IReadOnlyList<string> args, RuntimeEnvironment runtime)
    {
        ArgumentNullException.ThrowIfNull(args);
        ArgumentNullException.ThrowIfNull(runtime);

        var host = OptionValue(args, "--host") ?? DefaultHost;
        var portText = OptionValue(args, "--port") ?? NullIfBlank(runtime.Get("PORT"));
        if (portText is null)
        {
            return new ServerListenOptions(host, DefaultPort);
        }

        if (!int.TryParse(portText.Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out var port) || port is < 1 or > 65535)
        {
            throw new WeirConfigurationException($"Invalid port {portText!}: expected a number from 1 to 65535.");
        }

        return new ServerListenOptions(host, port);
    }

    private static string? OptionValue(IReadOnlyList<string> args, string name)
    {
        for (var i = 0; i < args.Count; i++)
        {
            if (args[i] != name)
            {
                continue;
            }

            if (i + 1 >= args.Count)
            {
                throw new WeirConfigurationException($"Missing value for {name}.");
            }

            return args[i + 1];
        }

        return null;
    }

    private static string? NullIfBlank(string? value) => string.IsNullOrWhiteSpace(value) ? null : value;
}
