using Weir.Core.Configuration;

namespace Weir.Core.Tests;

internal static class TestRuntime
{
    /// <summary>A runtime for the real OS with a fixed home and working directory under the temp folder.</summary>
    public static RuntimeEnvironment With(params (string Name, string Value)[] variables)
    {
        var root = Path.Join(Path.GetTempPath(), "weir-core-tests");
        var dictionary = variables.ToDictionary(v => v.Name, v => v.Value, StringComparer.Ordinal);
        if (!dictionary.ContainsKey("WEIR_HOME"))
        {
            dictionary["WEIR_HOME"] = Path.Join(root, "home");
        }

        return new RuntimeEnvironment(dictionary, OperatingSystem.IsWindows(), Path.Join(root, "user"), Path.Join(root, "cwd"));
    }

    /// <summary>A runtime with no variables at all (not even WEIR_HOME).</summary>
    public static RuntimeEnvironment Bare(bool isWindows, params (string Name, string Value)[] variables)
    {
        var root = Path.Join(Path.GetTempPath(), "weir-core-tests");
        return new RuntimeEnvironment(
            variables.ToDictionary(v => v.Name, v => v.Value, StringComparer.Ordinal),
            isWindows,
            Path.Join(root, "user"),
            Path.Join(root, "cwd"));
    }

    public static WeirOptions Load(params (string Name, string Value)[] variables) => WeirOptionsLoader.Load(With(variables));
}

/// <summary>A clock the test moves by hand.</summary>
internal sealed class ManualTimeProvider : TimeProvider
{
    private long _ticks = 1_000_000;

    public override long TimestampFrequency => TimeSpan.TicksPerSecond;

    public override long GetTimestamp() => _ticks;

    public void Advance(TimeSpan by) => _ticks += by.Ticks;
}
