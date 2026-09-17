using System.Runtime.InteropServices;
using Weir.Core.LibraryMode;
using Weir.Infrastructure.LibraryMode;

namespace Weir.Infrastructure.Tests.LibraryMode;

/// <summary>Link count detection on real files (issue #508's test list), including a real hard link.</summary>
public sealed class HardlinkInspectorTests : IDisposable
{
    private readonly string _folder = Path.Join(Path.GetTempPath(), "weir-hardlink-tests-" + Guid.NewGuid().ToString("N"));

    public HardlinkInspectorTests()
    {
        Directory.CreateDirectory(_folder);
    }

    public void Dispose()
    {
        try
        {
            Directory.Delete(_folder, recursive: true);
        }
        catch (IOException)
        {
        }
    }

    [Fact]
    public void An_ordinary_file_reports_a_link_count_of_one()
    {
        var path = Path.Join(_folder, "solo.mkv");
        File.WriteAllText(path, "content");

        Assert.Equal(1, PhysicalHardlinkInspector.Instance.LinkCount(path));
    }

    [Fact]
    public void A_real_hard_link_is_detected_and_skipped_by_the_policy()
    {
        var original = Path.Join(_folder, "Movie (2020).mkv");
        var link = Path.Join(_folder, "Movie (2020).seeding.mkv");
        File.WriteAllText(original, "content");

        if (!TestHardLinks.TryCreate(link, original))
        {
            return; // e.g. no admin/dev-mode privilege on this CI runner's filesystem; not what this test proves.
        }

        var linkCount = PhysicalHardlinkInspector.Instance.LinkCount(original);

        Assert.Equal(2, linkCount);
        Assert.True(HardlinkPolicy.Evaluate(linkCount, cleanHardlinkedFiles: false).Skip);
        Assert.False(HardlinkPolicy.Evaluate(linkCount, cleanHardlinkedFiles: true).Skip);
    }

    [Fact]
    public void A_missing_file_throws_rather_than_reporting_a_link_count()
    {
        var missing = Path.Join(_folder, "missing.mkv");
        Assert.ThrowsAny<IOException>(() => PhysicalHardlinkInspector.Instance.LinkCount(missing));
    }
}

/// <summary>
/// A hard link, for tests only. Mirrors <c>Weir.Infrastructure.Refiner.RemuxPass.FileLifecycle.CreateHardLink</c>'s
/// approach on the branches that already carry it (issue #522 part 3 / #506, neither on <c>main</c> yet) rather
/// than depending on either. Classic <see cref="DllImportAttribute"/> here (not the source-generated
/// <c>LibraryImportAttribute</c> production code uses) so this test-only helper needs no <c>AllowUnsafeBlocks</c>.
/// </summary>
internal static class TestHardLinks
{
    public static bool TryCreate(string link, string existing)
    {
        if (OperatingSystem.IsWindows())
        {
            return CreateHardLinkW(link, existing, IntPtr.Zero);
        }

        if (OperatingSystem.IsLinux())
        {
            try
            {
                return UnixLink(existing, link) == 0;
            }
            catch (Exception exception) when (exception is DllNotFoundException or EntryPointNotFoundException)
            {
                return false;
            }
        }

        return false;
    }

    [DllImport("kernel32.dll", EntryPoint = "CreateHardLinkW", SetLastError = true, CharSet = CharSet.Unicode)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateHardLinkW(string newFileName, string existingFileName, IntPtr securityAttributes);

    [DllImport("libc", EntryPoint = "link", SetLastError = true, CharSet = CharSet.Ansi)]
    private static extern int UnixLink(string existing, string link);
}
