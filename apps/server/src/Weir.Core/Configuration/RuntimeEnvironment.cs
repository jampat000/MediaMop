namespace Weir.Core.Configuration;

/// <summary>
/// The process facts configuration depends on, passed in so loading stays free of IO and
/// can be tested for any platform.
/// </summary>
/// <param name="Variables">Environment variables (names are case-sensitive, as in Python's <c>os.environ</c> on Linux).</param>
/// <param name="IsWindows">Whether Windows path rules and defaults apply.</param>
/// <param name="UserHomeDirectory">What <c>~</c> expands to.</param>
/// <param name="CurrentDirectory">What relative paths resolve against.</param>
public sealed record RuntimeEnvironment(
    IReadOnlyDictionary<string, string> Variables,
    bool IsWindows,
    string UserHomeDirectory,
    string CurrentDirectory)
{
    /// <summary>The variable's value, or <see langword="null"/> when it is not set.</summary>
    public string? Get(string name) => Variables.TryGetValue(name, out var value) ? value : null;

    /// <summary>Whether the variable is present at all, even if empty (Python's <c>name in os.environ</c>).</summary>
    public bool IsSet(string name) => Variables.ContainsKey(name);
}
