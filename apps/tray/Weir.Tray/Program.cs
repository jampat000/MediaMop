using System.Diagnostics;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Win32;
using Velopack;
using Velopack.Sources;

namespace Weir.Tray;

static class Program
{
    private const string MutexName = @"Local\WeirTrayHostSingleton";
    internal const int HealthTimeoutSeconds = 60;
    internal const int ServerStopTimeoutMs = 10_000;
    internal const double BrowserDebounceCooldownMs = 1250;
    internal const string GitHubRepo = "https://github.com/jampat000/Weir";
    internal const string UpgradeSettingsPath = "/settings?tab=upgrade";

    [STAThread]
    static int Main(string[] args)
    {
        VelopackApp.Build()
            .OnAfterInstallFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: after install v{v}");
                KillRunningProcesses($"Velopack after install v{v}");
                RegisterStartup();
            })
            .OnBeforeUninstallFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: before uninstall v{v}");
                KillRunningProcesses($"Velopack before uninstall v{v}");
                DeregisterStartup();
            })
            .OnBeforeUpdateFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: before update to v{v}");
            })
            .OnAfterUpdateFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: after update to v{v}");
                RegisterStartup();
            })
            .Run();

        if (args.Contains("--version"))
        {
            Console.WriteLine(typeof(Program).Assembly
                .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
                ?.InformationalVersion ?? "unknown");
            return 0;
        }

        bool noBrowser = args.Contains("--no-browser");

        using var mutex = new Mutex(false, MutexName, out bool createdNew);
        if (!createdNew)
        {
            AppendFallbackLog("Tray host launch skipped: an existing Weir tray instance is already running.");
            if (PortChoice.SuppliedPort(args, Environment.GetEnvironmentVariable) is { } ignored)
                AppendFallbackLog($"Ignoring {ignored.Source} {ignored.Text}: Weir is already running. Use \"Change port\" from its tray menu, or quit it and start it again with the new port.");
            if (!noBrowser)
                OpenExistingInstanceBrowser();
            return 0;
        }

        try
        {
            // Before any window, including the port dialog.
            ApplicationConfiguration.Initialize();

            var runtimeHome = RuntimeHome();
            Directory.CreateDirectory(runtimeHome);
            var port = ResolvePort(args, runtimeHome);
            if (port is null)
                return 1;

            var app = new TrayApp(port.Value, openBrowserOnReady: !noBrowser);
            app.Run();
            return 0;
        }
        catch (Exception ex)
        {
            AppendFallbackLog($"Fatal startup error:\n{ex}");
            return 1;
        }
    }

    /// <summary>
    /// The port to run on: supplied on the command line or in WEIR_PORT, else saved by an
    /// earlier run, else chosen now — by the person if there is one, by the default if not.
    /// Null means do not start; the reason is in tray-host.log.
    /// </summary>
    private static int? ResolvePort(string[] args, string runtimeHome)
    {
        var supplied = PortChoice.SuppliedPort(args, Environment.GetEnvironmentVariable);
        var saved = PortChoice.LoadSaved(runtimeHome);
        var interactive = PortChoice.HasInteractiveDesktop();

        // A server left behind by a tray that crashed still holds our port, and would make
        // the saved port look taken by "another program". This tray holds the session's
        // singleton mutex, so any WeirServer.exe from this install in this session is an orphan.
        StopOrphanedServers();

        var decision = PortChoice.Decide(
            supplied,
            saved,
            interactive,
            PortChoice.IsInUse,
            prompt => PortDialog.Ask(prompt, PortChoice.IsInUse, LoadAppIcon()));

        AppendFallbackLog($"Port: {decision.Reason} (interactive desktop: {(interactive ? "yes" : "no")})");
        if (decision.Port is { } port && decision.Save)
        {
            PortChoice.Save(runtimeHome, port);
            AppendFallbackLog($"Saved port {port} to {Path.Combine(runtimeHome, PortChoice.SavedPortFileName)}.");
        }
        return decision.Port;
    }

    private static void StopOrphanedServers() =>
        InstallProcesses.StopOwn(InstallProcesses.Root(), sameSessionOnly: true, AppendFallbackLog, "Startup (orphaned server check)");

    internal static Icon LoadAppIcon()
    {
        var assembly = Assembly.GetExecutingAssembly();
        var resourceName = assembly.GetManifestResourceNames()
            .FirstOrDefault(n => n.EndsWith("weir-tray-icon.ico", StringComparison.OrdinalIgnoreCase));

        if (resourceName is not null)
        {
            using var stream = assembly.GetManifestResourceStream(resourceName)!;
            return new Icon(stream);
        }

        var fileCandidates = new[]
        {
            Path.Combine(AppContext.BaseDirectory, "weir-tray-icon.ico"),
            Path.Combine(AppContext.BaseDirectory, "assets", "weir-tray-icon.ico"),
        };
        foreach (var path in fileCandidates)
        {
            if (File.Exists(path))
                return new Icon(path);
        }

        return SystemIcons.Application;
    }

    private static void OpenExistingInstanceBrowser()
    {
        try
        {
            var portFile = Path.Combine(RuntimeHome(), "current-port.txt");
            if (!File.Exists(portFile)) return;
            var text = File.ReadAllText(portFile).Trim();
            if (int.TryParse(text, out int port) && port is >= 1 and <= 65535)
                OpenBrowser(port);
        }
        catch { }
    }

    // Velopack's install and uninstall hooks: stop this install's own tray and server so their
    // files can be replaced or removed. Only this install's — see InstallProcesses.
    private static void KillRunningProcesses(string why) =>
        InstallProcesses.StopOwn(InstallProcesses.Root(), sameSessionOnly: false, AppendFallbackLog, why);

    private static void RegisterStartup()
    {
        try
        {
            var exe = Environment.ProcessPath;
            if (string.IsNullOrEmpty(exe)) return;
            using var key = Registry.CurrentUser.OpenSubKey(
                @"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", writable: true);
            key?.SetValue("Weir", $"\"{exe}\" --no-browser");
            AppendFallbackLog(@"Registered Weir startup (HKCU\Run).");

            // Remove any manually-created startup folder shortcut so there is only one entry.
            var shortcut = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Startup), "Weir.lnk");
            if (File.Exists(shortcut))
            {
                File.Delete(shortcut);
                AppendFallbackLog("Removed legacy startup folder shortcut.");
            }
        }
        catch (Exception ex)
        {
            AppendFallbackLog($"Could not register startup: {ex.Message}");
        }
    }

    private static void DeregisterStartup()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(
                @"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", writable: true);
            key?.DeleteValue("Weir", throwOnMissingValue: false);
            AppendFallbackLog(@"Deregistered Weir startup (HKCU\Run).");

            var shortcut = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Startup), "Weir.lnk");
            if (File.Exists(shortcut))
            {
                File.Delete(shortcut);
                AppendFallbackLog("Removed startup folder shortcut.");
            }
        }
        catch (Exception ex)
        {
            AppendFallbackLog($"Could not deregister startup: {ex.Message}");
        }
    }

    internal static string RuntimeHome()
    {
        var env = Environment.GetEnvironmentVariable("WEIR_HOME")?.Trim();
        if (!string.IsNullOrEmpty(env))
            return Path.GetFullPath(env);
        var programData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        if (string.IsNullOrEmpty(programData))
            programData = @"C:\ProgramData";
        return Path.Combine(programData, "Weir");
    }

    internal static bool OpenBrowser(
        int port,
        Action<ProcessStartInfo>? startProcess = null,
        string relativePath = "/")
    {
        if (!relativePath.StartsWith('/') || relativePath.StartsWith("//"))
            throw new ArgumentException("Browser path must be local to Weir.", nameof(relativePath));

        var startInfo = new ProcessStartInfo
        {
            FileName = $"http://127.0.0.1:{port}{relativePath}",
            UseShellExecute = true,
        };

        try
        {
            (startProcess ?? (info => Process.Start(info)))(startInfo);
            return true;
        }
        catch (Exception ex)
        {
            // Opening a browser is a convenience action. Session 0, disconnected RDP
            // sessions, and hardened shell policies can reject shell execution; none of
            // those conditions should stop the tray watchdog or its server process.
            AppendFallbackLog($"Could not open Weir in the browser: {ex.Message}");
            return false;
        }
    }

    internal static string? TrayUpdateFallbackPath(bool isInstalled) =>
        isInstalled ? null : UpgradeSettingsPath;

    internal static void AppendFallbackLog(string message)
    {
        try
        {
            var logPath = Path.Combine(RuntimeHome(), "tray-host.log");
            Directory.CreateDirectory(Path.GetDirectoryName(logPath)!);
            var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
            File.AppendAllText(logPath, $"[{timestamp}] {message}\n");
        }
        catch { }
    }
}

// ---------------------------------------------------------------------------
// Update settings — persisted as JSON in runtime home
// ---------------------------------------------------------------------------

[JsonConverter(typeof(JsonStringEnumConverter))]
enum UpdateMode
{
    Auto,
    DownloadOnly,
    NotifyOnly,
}

sealed class UpdateSettings
{
    public UpdateMode Mode { get; set; } = UpdateMode.Auto;
    public bool CheckOnStartup { get; set; } = true;
    public int CheckIntervalMinutes { get; set; } = 60;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    internal static UpdateSettings Load(string runtimeHome)
    {
        var path = Path.Combine(runtimeHome, "update-settings.json");
        // No file is a fresh install: nobody has chosen yet, so the shipped default applies.
        if (!File.Exists(path)) return new UpdateSettings();
        try
        {
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<UpdateSettings>(json, JsonOptions)
                ?? throw new InvalidDataException("update-settings.json parsed as null.");
        }
        catch (Exception ex)
        {
            // A file that exists but cannot be read is a different situation from no file:
            // it means a choice was made and we cannot tell what it was. Auto is the only
            // mode that installs an update with nobody watching, so guessing it is the one
            // guess that can act against an explicit choice — an operator who picked
            // NotifyOnly would be auto-updated by a truncated file. This is the read that
            // decides whether to install, so it matters more here than in the backend copy
            // it deliberately mirrors (get_update_settings in update_service.py).
            Program.AppendFallbackLog(
                $"update-settings.json could not be read ({ex.Message}). Using NotifyOnly so a damaged "
                + "file cannot install an update the operator did not choose.");
            return new UpdateSettings { Mode = UpdateMode.NotifyOnly };
        }
    }

    internal void Save(string runtimeHome)
    {
        var path = Path.Combine(runtimeHome, "update-settings.json");
        Directory.CreateDirectory(runtimeHome);
        // Written whole and then renamed. WriteAllText truncates first, so a crash mid-write
        // leaves exactly the half-file Load has to guess its way around; the point of that
        // fallback is to stay unreachable in practice.
        //
        // The scratch name is unique per write, not "update-settings.json.tmp". The backend
        // writes this same file when the Settings page saves, and a shared scratch name lets
        // one writer rename the other's file into place — an operator told their choice was
        // saved while the file holds a different one. Same directory, so the rename stays
        // atomic; leading dot so a half-written file is not mistaken for real settings.
        var tmp = Path.Combine(runtimeHome, $".update-settings.{Guid.NewGuid():n}.tmp");
        try
        {
            File.WriteAllText(tmp, JsonSerializer.Serialize(this, JsonOptions));
            File.Move(tmp, path, overwrite: true);
        }
        catch
        {
            if (File.Exists(tmp)) File.Delete(tmp);
            throw;
        }
    }
}

// ---------------------------------------------------------------------------
// Update service — manages check / download / apply lifecycle
// ---------------------------------------------------------------------------

sealed class UpdateService
{
    private readonly UpdateManager _mgr;
    private readonly string _runtimeHome;
    private readonly Action<string> _log;
    private UpdateInfo? _pendingUpdate;
    private bool _downloaded;
    private int _downloadProgress;

    internal bool HasPendingUpdate => _pendingUpdate is not null;
    internal bool IsDownloaded => _downloaded;
    internal int DownloadProgress => _downloadProgress;
    internal string? PendingVersion => _pendingUpdate?.TargetFullRelease?.Version?.ToString();

    internal UpdateService(string runtimeHome, Action<string> log)
    {
        _runtimeHome = runtimeHome;
        _log = log;

        var source = new GithubSource(Program.GitHubRepo, accessToken: null, prerelease: false);
        _mgr = new UpdateManager(source);
    }

    internal bool IsInstalled => _mgr.IsInstalled;

    internal async Task<bool> CheckForUpdateAsync()
    {
        try
        {
            _log("Checking for updates...");
            var info = await _mgr.CheckForUpdatesAsync();
            if (info is null)
            {
                _log("No update available.");
                _pendingUpdate = null;
                _downloaded = false;
                return false;
            }
            _pendingUpdate = info;
            _downloaded = false;
            _downloadProgress = 0;
            _log($"Update available: v{info.TargetFullRelease.Version}");
            return true;
        }
        catch (Exception ex)
        {
            _log($"Update check failed: {ex.Message}");
            return false;
        }
    }

    internal async Task<bool> DownloadUpdateAsync()
    {
        if (_pendingUpdate is null) return false;
        try
        {
            _log($"Downloading update v{_pendingUpdate.TargetFullRelease.Version}...");
            await _mgr.DownloadUpdatesAsync(_pendingUpdate, p => _downloadProgress = p);
            _downloaded = true;
            _log("Update downloaded successfully.");
            return true;
        }
        catch (Exception ex)
        {
            _log($"Update download failed: {ex.Message}");
            return false;
        }
    }

    internal void ApplyAndRestart(string[]? restartArgs = null)
    {
        if (!_downloaded || _pendingUpdate is null) return;
        _log($"Applying update v{_pendingUpdate.TargetFullRelease.Version} and restarting...");
        _mgr.ApplyUpdatesAndRestart(_pendingUpdate.TargetFullRelease, restartArgs);
    }

    internal void ApplyOnExit()
    {
        if (!_downloaded || _pendingUpdate is null) return;
        _log($"Scheduling update v{_pendingUpdate.TargetFullRelease.Version} to apply on exit...");
        _mgr.WaitExitThenApplyUpdates(_pendingUpdate.TargetFullRelease, silent: true, restart: true);
    }
}

// ---------------------------------------------------------------------------
// Tray application
// ---------------------------------------------------------------------------

sealed class TrayApp : IDisposable
{
    private readonly string _runtimeHome;
    private readonly string _installRoot;
    private volatile int _port;
    private readonly bool _openBrowserOnReady;
    private readonly string _logPath;
    private readonly object _logLock = new();
    private readonly object _browserLock = new();
    // Held while the server is being replaced, by the watchdog or by a port change, so the
    // two never start a server at the same time.
    private readonly object _serverLock = new();

    private NotifyIcon? _notifyIcon;
    private ToolStripMenuItem? _updateMenuItem;
    private ToolStripMenuItem? _portMenuItem;
    private volatile Process? _serverProcess;
    private double _lastBrowserOpenTicks;
    private CancellationTokenSource? _cts;
    private UpdateService? _updateService;
    private UpdateSettings _updateSettings;

    public TrayApp(int port, bool openBrowserOnReady)
    {
        _installRoot = AppContext.BaseDirectory;
        _runtimeHome = Program.RuntimeHome();
        _openBrowserOnReady = openBrowserOnReady;

        Directory.CreateDirectory(_runtimeHome);
        _logPath = Path.Combine(_runtimeHome, "tray-host.log");
        _port = port;
        _updateSettings = UpdateSettings.Load(_runtimeHome);

        Log($"Starting tray host. installRoot={_installRoot} runtimeHome={_runtimeHome}");
    }

    public void Run()
    {
        PrepareEnvironment();
        WritePortFile();
        Log($"Prepared runtime environment on port {_port}");

        StartServerProcess();
        Log("Waiting for local health endpoint");
        WaitForHealth();
        Log($"Weir is healthy on http://127.0.0.1:{_port}/");

        if (_openBrowserOnReady)
            OpenBrowserDebounced("startup");
        else
            Log("Skipping browser auto-open (no-browser mode).");

        _cts = new CancellationTokenSource();
        StartWatchdog();
        InitUpdateService();

        _notifyIcon = CreateNotifyIcon();
        _notifyIcon.Visible = true;

        Log("Starting tray icon event loop");
        Application.Run();
        Log("Tray icon event loop ended.");
    }

    // -- Environment setup --------------------------------------------------

    private void PrepareEnvironment()
    {
        var serverExeDir = FindServerExeDirectory();
        var webDist = Path.Combine(serverExeDir, "web-dist");
        if (!File.Exists(Path.Combine(webDist, "index.html")))
            throw new InvalidOperationException("Bundled web assets are missing from the Weir desktop package.");

        Environment.SetEnvironmentVariable("WEIR_ENV", "production");
        Environment.SetEnvironmentVariable("WEIR_HOME", _runtimeHome);
        Environment.SetEnvironmentVariable("WEIR_WEB_DIST", webDist);
        Environment.SetEnvironmentVariable("WEIR_SESSION_COOKIE_SECURE", "false");
        Environment.SetEnvironmentVariable("WEIR_SESSION_SECRET", EnsureSessionSecret());
    }

    private string EnsureSessionSecret()
    {
        var secretPath = Path.Combine(_runtimeHome, "session.secret");
        if (File.Exists(secretPath))
        {
            var existing = File.ReadAllText(secretPath).Trim();
            if (existing.Length >= 32)
                return existing;
        }

        var bytes = new byte[48];
        RandomNumberGenerator.Fill(bytes);
        var token = Convert.ToBase64String(bytes)
            .Replace("+", "-").Replace("/", "_").TrimEnd('=');
        Directory.CreateDirectory(_runtimeHome);
        File.WriteAllText(secretPath, token);
        return token;
    }

    // The port the server is listening on right now, for the second-launch "open in browser"
    // path in Program.OpenExistingInstanceBrowser. The saved choice is port.txt (PortChoice).
    private void WritePortFile()
    {
        File.WriteAllText(Path.Combine(_runtimeHome, "current-port.txt"), _port.ToString());
    }

    // -- Server process management ------------------------------------------

    private string FindServerExeDirectory()
    {
        var candidates = new[]
        {
            Path.Combine(_installRoot, "server", "WeirServer.exe"),
            Path.Combine(_installRoot, "WeirServer.exe"),
            Path.Combine(_installRoot, "..", "WeirServer.exe"),
        };
        foreach (var c in candidates)
        {
            if (File.Exists(c))
                return Path.GetDirectoryName(Path.GetFullPath(c))!;
        }
        return _installRoot;
    }

    private string FindServerExe()
    {
        var dir = FindServerExeDirectory();
        var exe = Path.Combine(dir, "WeirServer.exe");
        if (!File.Exists(exe))
            throw new FileNotFoundException("Bundled server host is missing.", exe);
        return exe;
    }

    private void StartServerProcess()
    {
        var serverExe = FindServerExe();
        Log($"Starting bundled server host: {serverExe}");

        _serverProcess = Process.Start(new ProcessStartInfo
        {
            FileName = serverExe,
            Arguments = $"--port {_port}",
            WorkingDirectory = Path.GetDirectoryName(serverExe),
            UseShellExecute = false,
            CreateNoWindow = true,
        });

        if (_serverProcess is null)
            throw new InvalidOperationException("Failed to start WeirServer.exe");

        Log($"Bundled server host pid={_serverProcess.Id}");
    }

    private void WaitForHealth()
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        var deadline = DateTime.UtcNow.AddSeconds(Program.HealthTimeoutSeconds);

        while (DateTime.UtcNow < deadline)
        {
            if (_serverProcess is { HasExited: true })
                throw new InvalidOperationException(
                    $"Weir server process exited unexpectedly with code {_serverProcess.ExitCode} before becoming healthy.");

            try
            {
                var response = client.GetAsync($"http://127.0.0.1:{_port}/ready").GetAwaiter().GetResult();
                if (response.StatusCode == HttpStatusCode.OK)
                    return;
            }
            catch (Exception) when (DateTime.UtcNow < deadline)
            {
                Thread.Sleep(250);
            }
        }

        throw new TimeoutException("Weir did not start listening on localhost in time.");
    }

    private Thread? _watchdog;

    private void StartWatchdog()
    {
        var ct = _cts!.Token;
        var thread = new Thread(() =>
        {
            int restartCount = 0;
            const int maxRestarts = 5;
            int[] backoffMs = [2_000, 5_000, 15_000, 30_000, 60_000];

            while (!ct.IsCancellationRequested)
            {
                Thread.Sleep(3000);
                if (ct.IsCancellationRequested) return;

                Process? proc;
                lock (_serverLock)
                {
                    proc = _serverProcess;
                    if (proc is null) return;
                    if (!proc.HasExited) continue;
                }

                Log($"Bundled server host exited unexpectedly with code {proc.ExitCode} (restart {restartCount + 1}/{maxRestarts})");

                if (restartCount >= maxRestarts)
                {
                    Log("Exceeded max restart attempts — giving up.");
                    try
                    {
                        _notifyIcon?.ShowBalloonTip(
                            8000, "Weir",
                            "Weir server failed repeatedly. Please restart Weir.",
                            ToolTipIcon.Error);
                    }
                    catch { }
                    return;
                }

                int delay = backoffMs[Math.Min(restartCount, backoffMs.Length - 1)];
                Log($"Waiting {delay}ms before restarting server...");
                Thread.Sleep(delay);
                if (ct.IsCancellationRequested) return;

                lock (_serverLock)
                {
                    // A port change may have replaced the server while this thread waited.
                    if (!ReferenceEquals(_serverProcess, proc)) continue;
                    try
                    {
                        StartServerProcess();
                        WaitForHealth();
                        Log($"Server restarted successfully (attempt {restartCount + 1}).");
                        restartCount = 0;
                    }
                    catch (Exception ex)
                    {
                        Log($"Server restart attempt {restartCount + 1} failed: {ex.Message}");
                        restartCount++;
                    }
                }
            }
        })
        {
            IsBackground = true,
            Name = "weir-server-watchdog",
        };
        _watchdog = thread;
        thread.Start();
    }

    private void StopServerProcess()
    {
        var proc = _serverProcess;
        if (proc is null || proc.HasExited) return;

        Log($"Stopping bundled server host pid={proc.Id}");
        try
        {
            proc.CloseMainWindow();
            if (!proc.WaitForExit(Program.ServerStopTimeoutMs))
            {
                Log($"Bundled server host pid={proc.Id} did not exit in time; killing it");
                proc.Kill(entireProcessTree: true);
                proc.WaitForExit(5000);
            }
        }
        catch (Exception ex)
        {
            Log($"Error stopping server: {ex.Message}");
            try { proc.Kill(entireProcessTree: true); } catch { }
        }
        finally
        {
            _serverProcess = null;
        }
    }

    // -- Update management --------------------------------------------------

    private void InitUpdateService()
    {
        _updateService = new UpdateService(_runtimeHome, Log);

        if (!_updateService.IsInstalled)
        {
            Log("Velopack: not installed (dev mode), skipping update checks.");
            return;
        }

        if (_updateSettings.CheckOnStartup)
            _ = RunUpdateCheckAsync();

        if (_updateSettings.CheckIntervalMinutes > 0)
            StartPeriodicUpdateCheck();

        StartApplyWatcher();
    }

    private void StartPeriodicUpdateCheck()
    {
        var ct = _cts!.Token;
        var intervalMs = _updateSettings.CheckIntervalMinutes * 60 * 1000;

        var thread = new Thread(async () =>
        {
            while (!ct.IsCancellationRequested)
            {
                try { await Task.Delay(intervalMs, ct); } catch (OperationCanceledException) { return; }
                await RunUpdateCheckAsync();
            }
        })
        {
            IsBackground = true,
            Name = "weir-update-check",
        };
        thread.Start();
    }

    private async Task RunUpdateCheckAsync()
    {
        if (_updateService is null) return;

        bool available = await _updateService.CheckForUpdateAsync();
        if (!available)
        {
            WriteUpdateState(false);
            return;
        }

        switch (_updateSettings.Mode)
        {
            case UpdateMode.Auto:
                if (await _updateService.DownloadUpdateAsync())
                {
                    WriteUpdateState(true, _updateService.PendingVersion);
                    _updateService.ApplyOnExit();
                    ShowUpdateScheduled();
                }
                break;

            case UpdateMode.DownloadOnly:
                if (await _updateService.DownloadUpdateAsync())
                {
                    WriteUpdateState(true, _updateService.PendingVersion);
                    ShowUpdateReady();
                }
                break;

            case UpdateMode.NotifyOnly:
                ShowUpdateAvailable();
                break;
        }
    }

    private void WriteUpdateState(bool downloaded, string? version = null)
    {
        try
        {
            var path = Path.Combine(_runtimeHome, "update-state.json");
            var json = JsonSerializer.Serialize(
                new { downloaded, version },
                new JsonSerializerOptions { WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
            File.WriteAllText(path, json);
        }
        catch (Exception ex)
        {
            Log($"Could not write update state: {ex.Message}");
        }
    }

    private void StartApplyWatcher()
    {
        var ct = _cts!.Token;
        var flagPath = Path.Combine(_runtimeHome, "update-apply-now");

        var thread = new Thread(async () =>
        {
            while (!ct.IsCancellationRequested)
            {
                try { await Task.Delay(5_000, ct); } catch (OperationCanceledException) { return; }

                if (!File.Exists(flagPath)) continue;
                if (_updateService?.IsDownloaded != true) continue;

                try { File.Delete(flagPath); } catch { }
                Log("Apply-now flag detected - applying update and restarting.");
                ApplyUpdateAndRestart();
                return;
            }
        })
        {
            IsBackground = true,
            Name = "weir-update-apply-watcher",
        };
        thread.Start();
    }

    private void ShowUpdateAvailable()
    {
        var version = _updateService?.PendingVersion ?? "new version";
        Log($"Notifying user: update v{version} available.");

        _notifyIcon?.ShowBalloonTip(
            8000, "Weir Update",
            $"Version {version} is available. Open Settings to update.",
            ToolTipIcon.Info);

        UpdateTrayMenuState();
    }

    private void ShowUpdateScheduled()
    {
        var version = _updateService?.PendingVersion ?? "new version";
        Log($"Notifying user: update v{version} will apply on next restart.");

        _notifyIcon?.ShowBalloonTip(
            8000, "Weir Update Ready",
            $"Version {version} has been downloaded and will be applied automatically on next restart.",
            ToolTipIcon.Info);

        UpdateTrayMenuState();
    }

    private void ShowUpdateReady()
    {
        var version = _updateService?.PendingVersion ?? "new version";
        Log($"Notifying user: update v{version} downloaded and ready to install.");

        _notifyIcon?.ShowBalloonTip(
            8000, "Weir Update Ready",
            $"Version {version} has been downloaded. Click here to restart and update.",
            ToolTipIcon.Info);

        if (_notifyIcon is not null)
            _notifyIcon.BalloonTipClicked += OnBalloonClickRestart;

        UpdateTrayMenuState();
    }

    private void OnBalloonClickRestart(object? sender, EventArgs e)
    {
        if (_notifyIcon is not null)
            _notifyIcon.BalloonTipClicked -= OnBalloonClickRestart;

        ApplyUpdateAndRestart();
    }

    private void ApplyUpdateAndRestart()
    {
        if (_updateService is null || !_updateService.IsDownloaded) return;

        Log("User requested update apply and restart.");
        StopServerProcess();
        _notifyIcon!.Visible = false;
        _updateService.ApplyAndRestart();
    }

    private void UpdateTrayMenuState()
    {
        if (_updateMenuItem is null || _updateService is null) return;

        if (_updateService.IsDownloaded)
        {
            _updateMenuItem.Text = $"Restart to update (v{_updateService.PendingVersion})";
            _updateMenuItem.Enabled = true;
            _updateMenuItem.Click -= OnUpdateMenuCheckClick;
            _updateMenuItem.Click += OnUpdateMenuRestartClick;
        }
        else if (_updateService.HasPendingUpdate)
        {
            _updateMenuItem.Text = $"Download update (v{_updateService.PendingVersion})";
            _updateMenuItem.Enabled = true;
            _updateMenuItem.Click -= OnUpdateMenuRestartClick;
            _updateMenuItem.Click += OnUpdateMenuDownloadClick;
        }
        else
        {
            _updateMenuItem.Text = "Check for updates";
            _updateMenuItem.Enabled = true;
        }
    }

    private async void OnUpdateMenuCheckClick(object? sender, EventArgs e)
    {
        if (_updateMenuItem is not null) _updateMenuItem.Enabled = false;
        await RunUpdateCheckAsync();
        if (_updateMenuItem is not null) _updateMenuItem.Enabled = true;
    }

    private async void OnUpdateMenuDownloadClick(object? sender, EventArgs e)
    {
        if (_updateService is null) return;
        if (_updateMenuItem is not null)
        {
            _updateMenuItem.Enabled = false;
            _updateMenuItem.Text = "Downloading update...";
        }
        if (await _updateService.DownloadUpdateAsync())
            ShowUpdateReady();
    }

    private void OnUpdateMenuRestartClick(object? sender, EventArgs e)
    {
        ApplyUpdateAndRestart();
    }

    // -- Tray icon ----------------------------------------------------------

    private NotifyIcon CreateNotifyIcon()
    {
        var icon = Program.LoadAppIcon();
        var menu = new ContextMenuStrip();

        var openItem = menu.Items.Add("Open Weir");
        openItem.Font = new Font(openItem.Font, FontStyle.Bold);
        openItem.Click += (_, _) => OpenBrowserDebounced("tray");

        menu.Items.Add("Open Data Folder").Click += (_, _) =>
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = _runtimeHome,
                UseShellExecute = true,
            });
        };

        _portMenuItem = new ToolStripMenuItem($"Change port ({_port})...");
        _portMenuItem.Click += (_, _) => OnChangePortClick();
        menu.Items.Add(_portMenuItem);

        menu.Items.Add(new ToolStripSeparator());

        _updateMenuItem = new ToolStripMenuItem("Check for updates");
        var updateFallbackPath = Program.TrayUpdateFallbackPath(
            _updateService is { IsInstalled: true });
        if (updateFallbackPath is null)
            _updateMenuItem.Click += OnUpdateMenuCheckClick;
        else
            _updateMenuItem.Click += (_, _) =>
                OpenBrowserDebounced("tray-update-settings", updateFallbackPath);
        menu.Items.Add(_updateMenuItem);

        menu.Items.Add(new ToolStripSeparator());

        menu.Items.Add("Quit").Click += (_, _) =>
        {
            Log("Quit requested from tray icon");
            if (_updateService is { IsDownloaded: true })
            {
                _updateService.ApplyOnExit();
                Log("Update will be applied after exit.");
            }
            StopServerProcess();
            _notifyIcon!.Visible = false;
            Application.Exit();
        };

        var notifyIcon = new NotifyIcon
        {
            Icon = icon,
            Text = "Weir",
            ContextMenuStrip = menu,
            Visible = false,
        };

        notifyIcon.DoubleClick += (_, _) => OpenBrowserDebounced("tray-dblclick");

        return notifyIcon;
    }

    // -- Port -------------------------------------------------------------

    private void OnChangePortClick()
    {
        var current = _port;
        var chosen = PortDialog.Ask(
            new PortPrompt(PortPromptReason.Change, current, CurrentPortInUse: false, Suggested: current),
            PortChoice.IsInUse,
            _notifyIcon?.Icon);
        if (chosen is not { } port || port == current)
        {
            Log("Change port: closed without a new port.");
            return;
        }

        if (_portMenuItem is not null)
        {
            _portMenuItem.Enabled = false;
            _portMenuItem.Text = $"Moving to port {port}...";
        }

        // Restarting waits up to a minute for the new server; keep the menu responsive.
        var ui = SynchronizationContext.Current;
        Task.Run(() => MoveToPort(current, port)).ContinueWith(_ =>
        {
            void Reset()
            {
                if (_portMenuItem is null) return;
                _portMenuItem.Enabled = true;
                _portMenuItem.Text = $"Change port ({_port})...";
            }
            if (ui is null) Reset();
            else ui.Post(_ => Reset(), null);
        });
    }

    private void MoveToPort(int from, int to)
    {
        lock (_serverLock)
        {
            Log($"Change port: restarting the server on port {to} (was {from}).");
            StopServerProcess();
            try
            {
                _port = to;
                StartServerProcess();
                WaitForHealth();
                PortChoice.Save(_runtimeHome, to);
                WritePortFile();
                Log($"Change port: Weir is healthy on http://127.0.0.1:{to}/ and port {to} is saved.");
                _notifyIcon?.ShowBalloonTip(8000, "Weir", $"Weir is now at http://localhost:{to}/", ToolTipIcon.Info);
                RestartWatchdogIfStopped();
                OpenBrowserDebounced("port-change");
            }
            catch (Exception ex)
            {
                // Put things back as they were rather than leave Weir down: the old port was
                // working a moment ago, and it is still the saved one.
                Log($"Change port: the server did not start on port {to} ({ex.Message}); going back to port {from}.");
                StopServerProcess();
                _port = from;
                try
                {
                    StartServerProcess();
                    WaitForHealth();
                    WritePortFile();
                    RestartWatchdogIfStopped();
                }
                catch (Exception back)
                {
                    Log($"Change port: could not restart on port {from} either: {back.Message}");
                }
                _notifyIcon?.ShowBalloonTip(
                    8000, "Weir",
                    $"Weir could not start on port {to}, so it is still at port {from}. See tray-host.log in the data folder.",
                    ToolTipIcon.Warning);
            }
        }
    }

    // The watchdog treats a cleared _serverProcess as shutdown and exits. A port change stops
    // and starts under _serverLock, so the watchdog should never see the gap; this guards the
    // case where it saw it anyway.
    private void RestartWatchdogIfStopped()
    {
        if (_watchdog is { IsAlive: true }) return;
        StartWatchdog();
    }

    // -- Browser ------------------------------------------------------------

    private void OpenBrowserDebounced(string source, string relativePath = "/")
    {
        var now = Environment.TickCount64;
        lock (_browserLock)
        {
            if (now - _lastBrowserOpenTicks < Program.BrowserDebounceCooldownMs)
            {
                Log($"Ignoring duplicate browser open request within debounce window (source={source}).");
                return;
            }
            _lastBrowserOpenTicks = now;
        }
        Log($"Opening Weir in browser on port {_port} (source={source})");
        Program.OpenBrowser(_port, relativePath: relativePath);
    }

    // -- Logging ------------------------------------------------------------

    private void Log(string message)
    {
        var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
        lock (_logLock)
        {
            try
            {
                File.AppendAllText(_logPath, $"[{timestamp}] {message}\n");
            }
            catch { }
        }
    }

    public void Dispose()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        StopServerProcess();
        _notifyIcon?.Dispose();
    }
}
