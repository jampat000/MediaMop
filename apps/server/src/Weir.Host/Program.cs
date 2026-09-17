using Weir.Core;
using Weir.Core.Configuration;
using Weir.Host;
using Weir.Infrastructure.Sqlite;

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
