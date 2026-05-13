using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;

namespace MediaMop.Tray;

static class Program
{
    private const string MutexName = @"Local\MediaMopTrayHostSingleton";
    internal const int PreferredPort = 8788;
    internal const int PortScanRange = 20;
    internal const int HealthTimeoutSeconds = 60;
    internal const int ServerStopTimeoutMs = 10_000;
    internal const double BrowserDebounceCooldownMs = 1250;

    [STAThread]
    static int Main(string[] args)
    {
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
    private Process? _serverProcess;
    private double _lastBrowserOpenTicks;
    private CancellationTokenSource? _watchdogCts;

    public TrayApp(bool openBrowserOnReady)
    {
        _installRoot = AppContext.BaseDirectory;
        _runtimeHome = Program.RuntimeHome();
        _openBrowserOnReady = openBrowserOnReady;

        Directory.CreateDirectory(_runtimeHome);
        _logPath = Path.Combine(_runtimeHome, "tray-host.log");
        _port = FindFreePort(Program.PreferredPort);

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

        StartWatchdog();

        ApplicationConfiguration.Initialize();
        _notifyIcon = CreateNotifyIcon();
        _notifyIcon.Visible = true;

        Log("Starting tray icon event loop");
        Application.Run();
    }

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
        _watchdogCts = new CancellationTokenSource();
        var ct = _watchdogCts.Token;

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
                            5000,
                            "MediaMop",
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

        menu.Items.Add("Quit").Click += (_, _) =>
        {
            Log("Quit requested from tray icon");
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
        _watchdogCts?.Cancel();
        _watchdogCts?.Dispose();
        StopServerProcess();
        _notifyIcon?.Dispose();
    }
}

