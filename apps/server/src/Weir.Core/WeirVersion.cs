using System.Reflection;

namespace Weir.Core;

/// <summary>
/// The version the server reports: <c>WEIR_VERSION</c> when set (as in Python's <c>get_version</c>),
/// otherwise the build's version, which MSBuild takes from <c>apps/backend/pyproject.toml</c>.
/// </summary>
public static class WeirVersion
{
    public static string Resolve(string? versionOverride) =>
        string.IsNullOrWhiteSpace(versionOverride) ? BuildVersion : versionOverride.Trim();

    public static string BuildVersion { get; } = ReadBuildVersion();

    private static string ReadBuildVersion()
    {
        var informational = typeof(WeirVersion).Assembly
            .GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
        if (string.IsNullOrWhiteSpace(informational))
        {
            return "0.0.0";
        }

        var plus = informational.IndexOf('+', StringComparison.Ordinal);
        return plus < 0 ? informational : informational[..plus];
    }
}
