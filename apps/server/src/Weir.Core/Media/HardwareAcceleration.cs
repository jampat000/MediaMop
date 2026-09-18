using System.Globalization;
using Weir.Core.Json;
using Weir.Core.Rules;

namespace Weir.Core.Media;

/// <summary>What ffmpeg on this machine says it can do (<c>AccelerationReport</c>).</summary>
public sealed record AccelerationReport
{
    /// <summary>Methods ffmpeg was compiled with, sorted. Not proof a device is present or working.</summary>
    public IReadOnlyList<string> AvailableMethods { get; init; } = [];

    public bool Detected { get; init; }

    /// <summary>Why detection produced nothing, when it did not.</summary>
    public string Detail { get; init; } = string.Empty;

    /// <summary>The vendors any available method belongs to, sorted.</summary>
    public IReadOnlyList<string> Vendors =>
        HardwareAcceleration.VendorMethods
            .Where(vendor => vendor.Value.Any(method => AvailableMethods.Contains(method, StringComparer.Ordinal)))
            .Select(vendor => vendor.Key)
            .Order(StringComparer.Ordinal)
            .ToList();
}

/// <summary>What the library asked for (<c>HardwareSettings</c>).</summary>
public sealed record HardwareSettings
{
    /// <summary><c>off</c>, <c>auto</c> or <c>device</c>; kept as text because the reference compares it un-normalized.</summary>
    public string Mode { get; init; } = HardwareAcceleration.ModeOff;

    /// <summary>The named method when <see cref="Mode"/> is <c>device</c>: <c>cuda</c>, <c>qsv</c>, <c>vaapi</c>.</summary>
    public string Device { get; init; } = string.Empty;

    public IReadOnlyList<string> DisabledVendors { get; init; } = [];

    public string Strictness { get; init; } = HardwareAcceleration.DefaultStrictness;

    public bool WantsHardware => Mode is HardwareAcceleration.ModeAuto or HardwareAcceleration.ModeDevice;
}

/// <summary>What Weir will actually ask ffmpeg for, and why (<c>AccelerationDecision</c>).</summary>
public sealed record AccelerationDecision
{
    public string Method { get; init; } = string.Empty;

    /// <summary>Flags that go before <c>-i</c>.</summary>
    public IReadOnlyList<string> ArgvFlags { get; init; } = [];

    public bool FellBackToSoftware { get; init; }

    public string Reason { get; init; } = string.Empty;

    public bool UsingHardware => Method.Length > 0;
}

/// <summary>
/// Hardware acceleration (<c>processing_hardware_acceleration.py</c>): reading <c>ffmpeg -hwaccels</c>, and
/// choosing a decode method that always degrades to software with a reason rather than failing a file.
/// </summary>
public static class HardwareAcceleration
{
    public const string ModeOff = "off";
    public const string ModeAuto = "auto";
    public const string ModeDevice = "device";

    /// <summary>ffmpeg's default strictness; passing it is the same as not passing the flag.</summary>
    public const string DefaultStrictness = "normal";

    /// <summary>
    /// Vendors an operator can switch off, and the ffmpeg hwaccel names each covers, in the reference's
    /// order (which decides the vendor of a method two vendors share, such as <c>d3d11va</c>).
    /// </summary>
    public static IReadOnlyList<KeyValuePair<string, IReadOnlyList<string>>> VendorMethods { get; } =
    [
        new("nvidia", ["cuda", "nvdec", "cuvid"]),
        new("intel", ["qsv", "d3d11va"]),
        new("amd", ["amf", "d3d11va"]),
        new("vaapi", ["vaapi"]),
        new("apple", ["videotoolbox"]),
    ];

    /// <summary>ffmpeg's strictness values, narrowest first.</summary>
    public static IReadOnlyList<string> StrictnessLevels { get; } = ["very", "strict", "normal", "unofficial", "experimental"];

    /// <summary>Auto mode's preference order, so the same machine picks the same device every run.</summary>
    public static IReadOnlyList<string> AutoPreference { get; } = ["cuda", "qsv", "vaapi", "videotoolbox", "d3d11va", "amf"];

    /// <summary>The report when ffmpeg could not be run at all (an <c>OSError</c> or <c>SubprocessError</c>).</summary>
    public static AccelerationReport ReportForRunError(string errorText) => new()
    {
        Detected = false,
        Detail = $"Weir could not ask ffmpeg which acceleration methods it supports ({errorText}).",
    };

    /// <summary>The report from <c>ffmpeg -hide_banner -hwaccels</c>'s exit code and stdout.</summary>
    public static AccelerationReport ReportFromHwaccels(int returnCode, string? stdout)
    {
        if (returnCode != 0)
        {
            return new AccelerationReport
            {
                Detected = false,
                Detail = "ffmpeg did not report its acceleration methods "
                    + $"(exit code {returnCode.ToString(CultureInfo.InvariantCulture)}). Weir will use software decoding.",
            };
        }

        var methods = new List<string>();
        foreach (var raw in PyText.SplitLines(stdout ?? string.Empty))
        {
            var line = Py.Lower(PyStrings.Strip(raw));
            // The first line is a heading; anything with whitespace is prose, not a method.
            if (line.Length == 0 || line.Contains(':', StringComparison.Ordinal) || line.Contains(' ', StringComparison.Ordinal))
            {
                continue;
            }

            if (line.All(c => c is (>= 'a' and <= 'z') or (>= '0' and <= '9') or '_'))
            {
                methods.Add(line);
            }
        }

        if (methods.Count == 0)
        {
            return new AccelerationReport
            {
                Detected = true,
                Detail = "This ffmpeg build reports no hardware acceleration methods, so decoding is done in software.",
            };
        }

        return new AccelerationReport
        {
            AvailableMethods = methods.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToList(),
            Detected = true,
            Detail = $"ffmpeg reports {methods.Count.ToString(CultureInfo.InvariantCulture)} acceleration method(s). Being listed does not prove a device is present.",
        };
    }

    /// <summary><c>decide_acceleration</c>: every path ends in a usable answer.</summary>
    public static AccelerationDecision Decide(HardwareSettings settings, AccelerationReport report)
    {
        ArgumentNullException.ThrowIfNull(settings);
        ArgumentNullException.ThrowIfNull(report);
        IReadOnlyList<string> strictFlags = settings.Strictness.Length > 0 && settings.Strictness != DefaultStrictness
            ? ["-strict", settings.Strictness]
            : [];

        if (!settings.WantsHardware)
        {
            return new AccelerationDecision
            {
                ArgvFlags = strictFlags,
                Reason = "Hardware decoding is switched off for this library, so Weir decoded in software.",
            };
        }

        if (!report.Detected || report.AvailableMethods.Count == 0)
        {
            return new AccelerationDecision
            {
                ArgvFlags = strictFlags,
                FellBackToSoftware = true,
                Reason = PyStrings.Strip(
                    "Weir fell back to software decoding because this ffmpeg build reports no hardware "
                    + $"acceleration. {report.Detail}"),
            };
        }

        if (settings.Mode == ModeDevice)
        {
            var wanted = Py.Lower(PyStrings.Strip(settings.Device));
            if (wanted.Length == 0)
            {
                return new AccelerationDecision
                {
                    ArgvFlags = strictFlags,
                    FellBackToSoftware = true,
                    Reason = "Weir fell back to software decoding because this library is set to use a named "
                        + "device but no device name was given.",
                };
            }

            if (!report.AvailableMethods.Contains(wanted, StringComparer.Ordinal))
            {
                return new AccelerationDecision
                {
                    ArgvFlags = strictFlags,
                    FellBackToSoftware = true,
                    Reason = $"Weir fell back to software decoding because the configured device '{wanted}' is not "
                        + $"one this ffmpeg build supports. It offers: {string.Join(", ", report.AvailableMethods)}.",
                };
            }

            if (!Allowed(wanted, settings.DisabledVendors))
            {
                return new AccelerationDecision
                {
                    ArgvFlags = strictFlags,
                    FellBackToSoftware = true,
                    Reason = $"Weir fell back to software decoding because '{wanted}' belongs to a vendor this "
                        + "library has switched off.",
                };
            }

            return new AccelerationDecision
            {
                Method = wanted,
                ArgvFlags = ["-hwaccel", wanted, .. strictFlags],
                Reason = $"Decoding with '{wanted}', as configured for this library.",
            };
        }

        foreach (var candidate in AutoPreference)
        {
            if (report.AvailableMethods.Contains(candidate, StringComparer.Ordinal) && Allowed(candidate, settings.DisabledVendors))
            {
                return new AccelerationDecision
                {
                    Method = candidate,
                    ArgvFlags = ["-hwaccel", candidate, .. strictFlags],
                    Reason = $"Chose '{candidate}' automatically from what this ffmpeg build offers.",
                };
            }
        }

        return new AccelerationDecision
        {
            ArgvFlags = strictFlags,
            FellBackToSoftware = true,
            Reason = "Weir fell back to software decoding because every acceleration method this ffmpeg build "
                + "offers belongs to a vendor this library has switched off.",
        };
    }

    /// <summary><c>parse_disabled_vendors</c>: known vendors only, first occurrence kept.</summary>
    public static IReadOnlyList<string> ParseDisabledVendors(string? csv)
    {
        var result = new List<string>();
        foreach (var raw in (csv ?? string.Empty).Split(','))
        {
            var name = Py.Lower(PyStrings.Strip(raw));
            if (VendorMethods.Any(v => v.Key == name) && !result.Contains(name, StringComparer.Ordinal))
            {
                result.Add(name);
            }
        }

        return result;
    }

    /// <summary><c>normalize_strictness</c>: unknown values mean ffmpeg's default.</summary>
    public static string NormalizeStrictness(string? raw)
    {
        var value = Py.Lower(PyStrings.Strip(raw ?? string.Empty));
        return StrictnessLevels.Contains(value, StringComparer.Ordinal) ? value : DefaultStrictness;
    }

    /// <summary><c>normalize_decode_mode</c>: unknown values mean off.</summary>
    public static string NormalizeDecodeMode(string? raw)
    {
        var value = Py.Lower(PyStrings.Strip(raw ?? string.Empty));
        return value is ModeOff or ModeAuto or ModeDevice ? value : ModeOff;
    }

    private static string? VendorOf(string method) =>
        VendorMethods.FirstOrDefault(v => v.Value.Contains(method, StringComparer.Ordinal)).Key;

    private static bool Allowed(string method, IReadOnlyList<string> disabled)
    {
        var vendor = VendorOf(method);
        return vendor is null || !disabled.Contains(vendor, StringComparer.Ordinal);
    }
}
