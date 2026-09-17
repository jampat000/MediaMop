using Weir.Core.Media;

namespace Weir.Core.Tests.Media;

/// <summary>
/// Ports of <c>tests/test_refiner_hardware_acceleration.py</c>. The rule every test checks: a device that is
/// busy, absent, or not compiled in falls back to software with a reason, and never fails a file. Detection
/// against a fake runner lives in <c>Weir.Infrastructure.Tests</c>; here, reading ffmpeg's answer.
/// </summary>
public sealed class HardwareAccelerationTests
{
    private static AccelerationReport Report(params string[] methods) => new() { AvailableMethods = methods, Detected = true, Detail = string.Empty };

    // --- detection -----------------------------------------------------------------------

    [Fact]
    public void Ffmpegs_reported_methods_are_parsed()
    {
        var report = HardwareAcceleration.ReportFromHwaccels(0, "Hardware acceleration methods:\ncuda\nvaapi\nqsv\n");

        Assert.True(report.Detected);
        Assert.Equal(["cuda", "qsv", "vaapi"], report.AvailableMethods.Order());
        Assert.Equal(["intel", "nvidia", "vaapi"], report.Vendors.Order());
        Assert.Contains("does not prove a device is present", report.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void A_build_with_no_acceleration_reports_none_and_says_so()
    {
        var report = HardwareAcceleration.ReportFromHwaccels(0, "Hardware acceleration methods:\n");

        Assert.True(report.Detected);
        Assert.Empty(report.AvailableMethods);
        Assert.Contains("no hardware acceleration methods", report.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void A_missing_ffmpeg_reports_nothing_rather_than_raising()
    {
        var report = HardwareAcceleration.ReportForRunError("no such file");

        Assert.False(report.Detected);
        Assert.Empty(report.AvailableMethods);
        Assert.Contains("could not ask ffmpeg", report.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void A_failing_ffmpeg_reports_nothing_rather_than_raising()
    {
        var report = HardwareAcceleration.ReportFromHwaccels(1, string.Empty);

        Assert.False(report.Detected);
        Assert.Contains("software decoding", report.Detail, StringComparison.Ordinal);
    }

    // --- choosing ------------------------------------------------------------------------

    [Fact]
    public void Off_is_the_default_and_passes_no_flags()
    {
        var decision = HardwareAcceleration.Decide(new HardwareSettings(), Report("cuda"));

        Assert.False(decision.UsingHardware);
        Assert.False(decision.FellBackToSoftware);
        Assert.Empty(decision.ArgvFlags);
        Assert.Contains("switched off", decision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Auto_picks_a_method_and_names_it()
    {
        var decision = HardwareAcceleration.Decide(new HardwareSettings { Mode = "auto" }, Report("vaapi", "cuda"));

        Assert.Equal("cuda", decision.Method);
        Assert.Equal(["-hwaccel", "cuda"], decision.ArgvFlags);
        Assert.Contains("automatically", decision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Auto_is_deterministic_so_the_same_machine_picks_the_same_device()
    {
        var report = Report("amf", "qsv", "cuda", "vaapi");

        var first = HardwareAcceleration.Decide(new HardwareSettings { Mode = "auto" }, report);
        var second = HardwareAcceleration.Decide(new HardwareSettings { Mode = "auto" }, report);

        Assert.Equal("cuda", first.Method);
        Assert.Equal(first.Method, second.Method);
    }

    [Fact]
    public void A_named_device_is_used_when_available()
    {
        var decision = HardwareAcceleration.Decide(new HardwareSettings { Mode = "device", Device = "qsv" }, Report("cuda", "qsv"));

        Assert.Equal("qsv", decision.Method);
        Assert.Equal(["-hwaccel", "qsv"], decision.ArgvFlags);
    }

    [Fact]
    public void Strictness_is_passed_only_when_it_differs_from_ffmpegs_own_default()
    {
        var normal = HardwareAcceleration.Decide(new HardwareSettings { Strictness = "normal" }, Report());
        var experimental = HardwareAcceleration.Decide(new HardwareSettings { Strictness = "experimental" }, Report());

        Assert.Empty(normal.ArgvFlags);
        Assert.Equal(["-strict", "experimental"], experimental.ArgvFlags);
    }

    // --- the fallback, which is the point ------------------------------------------------

    [Fact]
    public void No_acceleration_available_falls_back_and_records_why()
    {
        var decision = HardwareAcceleration.Decide(
            new HardwareSettings { Mode = "auto" },
            new AccelerationReport { Detected = true, Detail = "This ffmpeg build reports no hardware acceleration." });

        Assert.False(decision.UsingHardware);
        Assert.True(decision.FellBackToSoftware);
        Assert.Contains("fell back to software", decision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void A_configured_device_that_is_missing_falls_back_and_lists_what_there_is()
    {
        var decision = HardwareAcceleration.Decide(new HardwareSettings { Mode = "device", Device = "cuda" }, Report("vaapi", "qsv"));

        Assert.True(decision.FellBackToSoftware);
        Assert.Contains("'cuda' is not one this ffmpeg build supports", decision.Reason, StringComparison.Ordinal);
        Assert.Contains("vaapi", decision.Reason, StringComparison.Ordinal);
        Assert.Contains("qsv", decision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void A_device_mode_with_no_device_named_falls_back()
    {
        var decision = HardwareAcceleration.Decide(new HardwareSettings { Mode = "device" }, Report("cuda"));

        Assert.True(decision.FellBackToSoftware);
        Assert.Contains("no device name was given", decision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Ffmpeg_being_unavailable_entirely_falls_back()
    {
        var decision = HardwareAcceleration.Decide(
            new HardwareSettings { Mode = "auto" },
            new AccelerationReport { Detected = false, Detail = "Weir could not ask ffmpeg." });

        Assert.True(decision.FellBackToSoftware);
    }

    // --- the escape hatch ----------------------------------------------------------------

    [Fact]
    public void A_disabled_vendor_is_skipped_by_auto()
    {
        var decision = HardwareAcceleration.Decide(new HardwareSettings { Mode = "auto", DisabledVendors = ["nvidia"] }, Report("cuda", "vaapi"));

        Assert.Equal("vaapi", decision.Method);
    }

    [Fact]
    public void A_disabled_vendor_blocks_it_even_when_named_explicitly()
    {
        var decision = HardwareAcceleration.Decide(
            new HardwareSettings { Mode = "device", Device = "cuda", DisabledVendors = ["nvidia"] },
            Report("cuda"));

        Assert.True(decision.FellBackToSoftware);
        Assert.Contains("switched off", decision.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Disabling_every_available_vendor_falls_back_and_says_so()
    {
        var decision = HardwareAcceleration.Decide(
            new HardwareSettings { Mode = "auto", DisabledVendors = ["nvidia", "intel", "amd", "vaapi", "apple"] },
            Report("cuda", "qsv", "vaapi"));

        Assert.True(decision.FellBackToSoftware);
        Assert.Contains("every acceleration method", decision.Reason, StringComparison.Ordinal);
    }

    // --- parsing -------------------------------------------------------------------------

    [Fact]
    public void Only_known_vendors_are_accepted()
    {
        Assert.Equal(["nvidia", "intel"], HardwareAcceleration.ParseDisabledVendors("nvidia, NOT_A_VENDOR ,intel,nvidia"));
        Assert.Empty(HardwareAcceleration.ParseDisabledVendors(string.Empty));
        Assert.Empty(HardwareAcceleration.ParseDisabledVendors(null));
    }

    [Fact]
    public void Every_selectable_vendor_maps_to_at_least_one_method()
    {
        foreach (var (vendor, methods) in HardwareAcceleration.VendorMethods)
        {
            Assert.True(methods.Count > 0, vendor);
        }
    }

    [Fact]
    public void Unknown_modes_and_strictness_fall_back_to_the_current_behaviour()
    {
        Assert.Equal("off", HardwareAcceleration.NormalizeDecodeMode("something"));
        Assert.Equal("off", HardwareAcceleration.NormalizeDecodeMode(null));
        Assert.Equal(HardwareAcceleration.DefaultStrictness, HardwareAcceleration.NormalizeStrictness("something"));
        Assert.Equal(HardwareAcceleration.DefaultStrictness, HardwareAcceleration.NormalizeStrictness(null));
        foreach (var level in HardwareAcceleration.StrictnessLevels)
        {
            Assert.Equal(level, HardwareAcceleration.NormalizeStrictness(level));
        }
    }
}
