using Weir.Core;
using Weir.Core.Configuration;
using Weir.Host;
using Weir.Infrastructure.Auth;
using Weir.Infrastructure.Sqlite;

if (args.Length > 0 && string.Equals(args[0], "recover", StringComparison.Ordinal))
{
    // Local console access only: no HTTP route runs this. Reaching the server's own shell (and so
    // its database under WEIR_HOME) is the recovery factor — see RecoverCommand and #454/#553.
    try
    {
        return await RecoverCommand.RunAsync(
            args[1..],
            WeirServer.CurrentRuntime(),
            Console.Out,
            Console.Error,
            new ConsoleRecoverPasswordPrompt()).ConfigureAwait(false);
    }
    catch (WeirConfigurationException exception)
    {
        await Console.Error.WriteLineAsync($"Weir cannot start: {exception.Message}").ConfigureAwait(false);
        return 1;
    }
}

if (args.Contains("--version"))
{
    Console.WriteLine(WeirVersion.Resolve(Environment.GetEnvironmentVariable("WEIR_VERSION")));
    return 0;
}

WebApplication app;
try
{
    app = WeirServer.Build(args, WeirServer.CurrentRuntime());
}
catch (Exception exception) when (exception is WeirConfigurationException or DatabaseSchemaMismatchException)
{
    // Operator-facing refusals: print the message, not a stack trace.
    await Console.Error.WriteLineAsync($"Weir cannot start: {exception.Message}").ConfigureAwait(false);
    return 1;
}

await app.RunAsync().ConfigureAwait(false);
return 0;
