using System.Security.Cryptography;
using System.Text;
using TimeZoneConverter;
using Weir.Core.Configuration;
using Weir.Core.Json;
using Weir.Core.Settings;
using Weir.Core.Updates;

namespace Weir.Infrastructure.Runtime;

/// <summary>IANA zone names the way <c>zoneinfo.ZoneInfo</c> resolves them (with the tzdata package on Windows).</summary>
public sealed class IanaTimeZoneResolver : ITimeZoneResolver
{
    public bool TryFind(string name, out TimeZoneInfo zone)
    {
        zone = TimeZoneInfo.Utc;
        if (string.IsNullOrEmpty(name) || name.Contains('\0', StringComparison.Ordinal))
        {
            return false;
        }

        if (TZConvert.TryGetTimeZoneInfo(name, out var found))
        {
            zone = found;
            return true;
        }

        return false;
    }
}

/// <summary>The tray's update files under <c>WEIR_HOME</c> (port of the file side of <c>update_service</c>).</summary>
public sealed class UpdateFiles
{
    public const string SettingsFileName = "update-settings.json";
    public const string StateFileName = "update-state.json";
    public const string ApplyFlagFileName = "update-apply-now";

    private readonly WeirOptions _options;

    public UpdateFiles(WeirOptions options)
    {
        _options = options;
    }

    /// <summary><c>get_update_settings</c>, with <paramref name="warn"/> called when the file is unreadable.</summary>
    public PyDict ReadSettings(Action<string>? warn = null)
    {
        var path = Path.Join(_options.WeirHome, SettingsFileName);
        if (!File.Exists(path) && !Directory.Exists(path))
        {
            return UpdateStatus.DefaultUpdateSettings;
        }

        string text;
        try
        {
            text = File.ReadAllText(path, new UTF8Encoding(false, throwOnInvalidBytes: true));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DecoderFallbackException)
        {
            warn?.Invoke(path);
            return UpdateStatus.UnreadableUpdateSettings;
        }

        if (text.StartsWith('﻿'))
        {
            warn?.Invoke(path);
            return UpdateStatus.UnreadableUpdateSettings;
        }

        var parsed = UpdateStatus.ParseUpdateSettings(text);
        if (parsed is null)
        {
            warn?.Invoke(path);
            return UpdateStatus.UnreadableUpdateSettings;
        }

        return parsed;
    }

    /// <summary><c>put_update_settings</c>: written whole to a unique scratch file, then renamed into place.</summary>
    public PyDict WriteSettings(string mode, bool checkOnStartup, long checkIntervalMinutes)
    {
        var path = Path.Join(_options.WeirHome, SettingsFileName);
        var text = UpdateStatus.SerializeUpdateSettings(mode, checkOnStartup, checkIntervalMinutes);
        if (OperatingSystem.IsWindows())
        {
            // Python writes in text mode, so newlines become CRLF on Windows.
            text = text.Replace("\n", "\r\n", StringComparison.Ordinal);
        }

        var directory = Path.GetDirectoryName(path)!;
        var scratch = Path.Join(directory, $".{SettingsFileName}.{Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(4))}.tmp");
        try
        {
            File.WriteAllBytes(scratch, Encoding.UTF8.GetBytes(text));
            File.Move(scratch, path, overwrite: true);
            scratch = string.Empty;
        }
        finally
        {
            if (scratch.Length > 0 && File.Exists(scratch))
            {
                File.Delete(scratch);
            }
        }

        return UpdateStatus.UpdateSettingsOut(mode, checkOnStartup, checkIntervalMinutes);
    }

    /// <summary><c>get_update_state</c>.</summary>
    public PyDict ReadState()
    {
        var path = Path.Join(_options.WeirHome, StateFileName);
        if (!File.Exists(path))
        {
            return UpdateStatus.ParseUpdateState(null);
        }

        try
        {
            return UpdateStatus.ParseUpdateState(File.ReadAllText(path, new UTF8Encoding(false, throwOnInvalidBytes: true)));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or DecoderFallbackException)
        {
            return UpdateStatus.ParseUpdateState(null);
        }
    }

    /// <summary><c>write_apply_update_flag</c>: <c>Path.touch()</c>.</summary>
    public void WriteApplyFlag()
    {
        var path = Path.Join(_options.WeirHome, ApplyFlagFileName);
        if (File.Exists(path))
        {
            File.SetLastWriteTimeUtc(path, DateTime.UtcNow);
            return;
        }

        using (File.Create(path))
        {
        }
    }

    /// <summary><c>_detect_install_type</c>: <c>WEIR_RUNTIME</c>, a Docker marker, a packaged Windows build, else source.</summary>
    public static string DetectInstallType(string? runtimeVariable)
    {
        var runtime = (runtimeVariable ?? string.Empty).Trim().ToLowerInvariant();
        if (runtime is "windows" or "docker" or "source")
        {
            return runtime;
        }

        if (File.Exists("/.dockerenv") || Directory.Exists("/.dockerenv"))
        {
            return "docker";
        }

        // A single-file publish is .NET's equivalent of a frozen (PyInstaller) build.
        var singleFile = string.IsNullOrEmpty(typeof(UpdateFiles).Assembly.Location);
        return singleFile && OperatingSystem.IsWindows() ? "windows" : "source";
    }
}
