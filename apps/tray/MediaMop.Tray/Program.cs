using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Velopack;
using Velopack.Sources;

namespace MediaMop.Tray;

static class Program
{
    private const string MutexName = @"Local\MediaMopTrayHostSingleton";
    internal const int PreferredPort = 8788;
    internal const int PortScanRange = 20;
    internal const int HealthTimeoutSeconds = 60;
    internal const int ServerStopTimeoutMs = 10_000;
    internal const double BrowserDebounceCooldownMs = 1250;
    internal const string GitHubRepo = "https://github.com/jampat000/MediaMop";

    [STAThread]
    static int Main(string[] args)
    {
        VelopackApp.Build()
            .OnAfterInstallFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: after install v{v}");
            })
            .OnBeforeUninstallFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: before uninstall v{v}");
            })
            .OnBeforeUpdateFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: before update to v{v}");
            })
            .OnAfterUpdateFastCallback((v) =>
            {
                AppendFallbackLog($"Velopack: after update to v{v}");
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
            AppendFallbackLog("Tray host launch skipped: an existing MediaMop tray instance is already running.");
            if (!noBrowser)
                OpenExistingInstanceBrowser();
            return 0;
        }

        try
        {
            var app = new TrayApp(openBrowserOnReady: !noBrowser);
            app.Run();
            return 0;
        }
        catch (Exception ex)
        {
            AppendFallbackLog($"Fatal startup error:\n{ex}");
            return 1;
        }
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

    internal static string RuntimeHome()
    {
        var env = Environment.GetEnvironmentVariable("MEDIAMOP_HOME")?.Trim();
        if (!string.IsNullOrEmpty(env))
            return Path.GetFullPath(env);
        var programData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
        if (string.IsNullOrEmpty(programData))
            programData = @"C:\ProgramData";
        return Path.Combine(programData, "MediaMop");
    }

    internal static void OpenBrowser(int port)
    {
        Process.Start(new ProcessStartInfo
        {
            FileName = $"http://127.0.0.1:{port}/",
            UseShellExecute = true,
        });
    }

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
        if (!File.Exists(path)) return new UpdateSettings();
        try
        {
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<UpdateSettings>(json, JsonOptions) ?? new UpdateSettings();
        }
        catch { return new UpdateSettings(); }
    }

    internal void Save(string runtimeHome)
    {
        var path = Path.Combine(runtimeHome, "update-settings.json");
        Directory.CreateDirectory(runtimeHome);
        File.WriteAllText(path, JsonSerializer.Serialize(this, JsonOptions));
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
    private readonly int _port;
    private readonly bool _openBrowserOnReady;
    private readonly string _logPath;
    private readonly object _logLock = new();
    private readonly object _browserLock = new();

    private NotifyIcon? _notifyIcon;
    private ToolStripMenuItem? _updateMenuItem;
    private Process? _serverProcess;
    private double _lastBrowserOpenTicks;
    private CancellationTokenSource? _cts;
    private UpdateService? _updateService;
    private UpdateSettings _updateSettings;

    public TrayApp(bool openBrowserOnReady)
    {
        _installRoot = AppContext.BaseDirectory;
        _runtimeHome = Program.RuntimeHome();
        _openBrowserOnReady = openBrowserOnReady;

        Directory.CreateDirectory(_runtimeHome);
        _logPath = Path.Combine(_runtimeHome, "tray-host.log");
        _port = FindFreePort(Program.PreferredPort);
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
        Log($"MediaMop is healthy on http://127.0.0.1:{_port}/");

        if (_openBrowserOnReady)
            OpenBrowserDebounced("startup");
        else
            Log("Skipping browser auto-open (no-browser mode).");

        _cts = new CancellationTokenSource();
        StartWatchdog();
        InitUpdateService();

        ApplicationConfiguration.Initialize();
        _notifyIcon = CreateNotifyIcon();
        _notifyIcon.Visible = true;

        Log("Starting tray icon event loop");
        Application.Run();
    }

    // -- Environment setup --------------------------------------------------

    private void PrepareEnvironment()
    {
        var serverExeDir = FindServerExeDirectory();
        var webDist = Path.Combine(serverExeDir, "_internal", "web-dist");
        if (!File.Exists(Path.Combine(webDist, "index.html")))
        {
            webDist = Path.Combine(serverExeDir, "web-dist");
            if (!File.Exists(Path.Combine(webDist, "index.html")))
                throw new InvalidOperationException("Bundled web assets are missing from the MediaMop desktop package.");
        }

        Environment.SetEnvironmentVariable("MEDIAMOP_ENV", "production");
        Environment.SetEnvironmentVariable("MEDIAMOP_HOME", _runtimeHome);
        Environment.SetEnvironmentVariable("MEDIAMOP_WEB_DIST", webDist);
        Environment.SetEnvironmentVariable("MEDIAMOP_SESSION_COOKIE_SECURE", "false");
        Environment.SetEnvironmentVariable("MEDIAMOP_SESSION_SECRET", EnsureSessionSecret());

        var alembicRoot = Path.Combine(serverExeDir, "_internal");
        if (File.Exists(Path.Combine(alembicRoot, "alembic.ini")))
            Environment.SetEnvironmentVariable("MEDIAMOP_ALEMBIC_ROOT", alembicRoot);
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

    private void WritePortFile()
    {
        File.WriteAllText(Path.Combine(_runtimeHome, "current-port.txt"), _port.ToString());
    }

    // -- Server process management ------------------------------------------

    private string FindServerExeDirectory()
    {
        var candidates = new[]
        {
            Path.Combine(_installRoot, "MediaMopServer.exe"),
            Path.Combine(_installRoot, "..", "MediaMopServer.exe"),
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
        var exe = Path.Combine(dir, "MediaMopServer.exe");
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
            Arguments = $"--serve --port {_port}",
            WorkingDirectory = Path.GetDirectoryName(serverExe),
            UseShellExecute = false,
            CreateNoWindow = true,
        });

        if (_serverProcess is null)
            throw new InvalidOperationException("Failed to start MediaMopServer.exe");

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
                    $"MediaMop server process exited unexpectedly with code {_serverProcess.ExitCode} before becoming healthy.");

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

        throw new TimeoutException("MediaMop did not start listening on localhost in time.");
    }

    private void StartWatchdog()
    {
        var ct = _cts!.Token;
        var thread = new Thread(() =>
        {
            while (!ct.IsCancellationRequested)
            {
                var proc = _serverProcess;
                if (proc is null) return;

                if (proc.HasExited)
                {
                    Log($"Bundled server host exited unexpectedly with code {proc.ExitCode}");
                    try
                    {
                        _notifyIcon?.ShowBalloonTip(
                            5000, "MediaMop",
                            "MediaMop server stopped unexpectedly. Please restart MediaMop.",
                            ToolTipIcon.Warning);
                    }
                    catch { }
                    return;
                }

                Thread.Sleep(3000);
            }
        })
        {
            IsBackground = true,
            Name = "mediamop-server-watchdog",
        };
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
            Name = "mediamop-update-check",
        };
        thread.Start();
    }

    private async Task RunUpdateCheckAsync()
    {
        if (_updateService is null) return;

        bool available = await _updateService.CheckForUpdateAsync();
        if (!available) return;

        switch (_updateSettings.Mode)
        {
            case UpdateMode.Auto:
                if (await _updateService.DownloadUpdateAsync())
                    ShowUpdateReady();
                break;

            case UpdateMode.DownloadOnly:
                if (await _updateService.DownloadUpdateAsync())
                    ShowUpdateReady();
                break;

            case UpdateMode.NotifyOnly:
                ShowUpdateAvailable();
                break;
        }
    }

    private void ShowUpdateAvailable()
    {
        var version = _updateService?.PendingVersion ?? "new version";
        Log($"Notifying user: update v{version} available.");

        _notifyIcon?.ShowBalloonTip(
            8000, "MediaMop Update",
            $"Version {version} is available. Open Settings to update.",
            ToolTipIcon.Info);

        UpdateTrayMenuState();
    }

    private void ShowUpdateReady()
    {
        var version = _updateService?.PendingVersion ?? "new version";
        Log($"Notifying user: update v{version} downloaded and ready to install.");

        _notifyIcon?.ShowBalloonTip(
            8000, "MediaMop Update Ready",
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
        var icon = LoadIcon();
        var menu = new ContextMenuStrip();

        var openItem = menu.Items.Add("Open MediaMop");
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

        menu.Items.Add(new ToolStripSeparator());

        _updateMenuItem = new ToolStripMenuItem("Check for updates");
        _updateMenuItem.Click += OnUpdateMenuCheckClick;
        if (_updateService is null || !_updateService.IsInstalled)
            _updateMenuItem.Visible = false;
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

        return new NotifyIcon
        {
            Icon = icon,
            Text = "MediaMop",
            ContextMenuStrip = menu,
            Visible = false,
        };
    }

    private Icon LoadIcon()
    {
        var assembly = Assembly.GetExecutingAssembly();
        var resourceName = assembly.GetManifestResourceNames()
            .FirstOrDefault(n => n.EndsWith("mediamop-tray-icon.ico", StringComparison.OrdinalIgnoreCase));

        if (resourceName is not null)
        {
            using var stream = assembly.GetManifestResourceStream(resourceName)!;
            return new Icon(stream);
        }

        var fileCandidates = new[]
        {
            Path.Combine(_installRoot, "mediamop-tray-icon.ico"),
            Path.Combine(_installRoot, "assets", "mediamop-tray-icon.ico"),
        };
        foreach (var path in fileCandidates)
        {
            if (File.Exists(path))
                return new Icon(path);
        }

        return SystemIcons.Application;
    }

    // -- Browser ------------------------------------------------------------

    private void OpenBrowserDebounced(string source)
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
        Log($"Opening MediaMop in browser on port {_port} (source={source})");
        Program.OpenBrowser(_port);
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

    // -- Utilities ----------------------------------------------------------

    private static int FindFreePort(int preferred)
    {
        for (int port = preferred; port < preferred + Program.PortScanRange; port++)
        {
            try
            {
                using var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
                socket.Bind(new IPEndPoint(IPAddress.Loopback, port));
                return port;
            }
            catch (SocketException) { }
        }
        throw new InvalidOperationException("Could not find a free localhost port for MediaMop.");
    }

    public void Dispose()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        StopServerProcess();
        _notifyIcon?.Dispose();
    }
}
