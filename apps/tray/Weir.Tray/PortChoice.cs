using System.Globalization;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace Weir.Tray;

// ---------------------------------------------------------------------------
// Which port Weir listens on, and how that choice is made and kept.
//
// The tray used to re-pick a free port on every start and remember nothing, so a user
// whose port was busy once got a different address next time and their bookmark broke.
// Now the port is chosen once — by the person, or by an administrator on the command
// line — saved under the runtime home, and reused. It never moves on its own.
// ---------------------------------------------------------------------------

/// <summary>Why the port dialog is being shown.</summary>
enum PortPromptReason
{
    /// <summary>First run on an interactive desktop, nothing supplied.</summary>
    FirstRun,

    /// <summary>The saved port is taken by another program on a later start.</summary>
    SavedPortBusy,

    /// <summary>The user picked "Change port" from the tray menu.</summary>
    Change,
}

/// <summary>What the dialog is asked, and what it should pre-fill.</summary>
sealed record PortPrompt(PortPromptReason Reason, int CurrentPort, bool CurrentPortInUse, int? Suggested);

/// <summary>
/// The outcome of deciding on a port at startup. <see cref="Port"/> is null when the tray
/// should not start (the person quit the dialog, or a headless start found its saved port
/// taken). <see cref="Save"/> says whether the port is a new choice to write to disk.
/// </summary>
sealed record PortDecision(int? Port, bool Save, string Reason);

static class PortChoice
{
    /// <summary>
    /// Weir's own default. It spells W-E-I-R on a phone keypad, is unassigned in the IANA
    /// registry (inside 9347-9373), and no common media-stack app listens on it.
    /// </summary>
    internal const int DefaultPort = 9347;

    /// <summary>How far above a busy port to look for a free one to suggest.</summary>
    internal const int ScanRange = 20;

    /// <summary>The environment variable an administrator can set instead of <c>--port</c>.</summary>
    internal const string PortEnvironmentVariable = "WEIR_PORT";

    internal const string SavedPortFileName = "port.txt";

    /// <summary>
    /// A port supplied without a person: <c>--port N</c> on the command line (which wins),
    /// otherwise <c>WEIR_PORT</c>. Returns the raw text and where it came from, or null.
    /// </summary>
    internal static (string Text, string Source)? SuppliedPort(IReadOnlyList<string> args, Func<string, string?> getEnv)
    {
        for (var i = 0; i < args.Count; i++)
        {
            if (string.Equals(args[i], "--port", StringComparison.OrdinalIgnoreCase))
                return (i + 1 < args.Count ? args[i + 1] : "", "--port");
            if (args[i].StartsWith("--port=", StringComparison.OrdinalIgnoreCase))
                return (args[i]["--port=".Length..], "--port");
        }

        var env = getEnv(PortEnvironmentVariable);
        return string.IsNullOrWhiteSpace(env) ? null : (env, PortEnvironmentVariable);
    }

    /// <summary>A whole number from 1 to 65535, or null.</summary>
    internal static int? ParsePort(string? text)
    {
        if (text is null) return null;
        return int.TryParse(text.Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out var port)
            && port is >= 1 and <= 65535
            ? port
            : null;
    }

    /// <summary>
    /// What is wrong with a port typed into the dialog, in words a person can act on, or null
    /// if it is fine. <paramref name="allowedInUse"/> is Weir's own current port when changing
    /// it: Weir's server is the program holding it, so it is not "in use by another program".
    /// </summary>
    internal static string? Validate(string? text, int? allowedInUse, Func<int, bool> isInUse)
    {
        if (string.IsNullOrWhiteSpace(text))
            return "Enter a port number.";
        if (ParsePort(text) is not { } port)
            return "A port is a whole number from 1 to 65535.";
        if (port != allowedInUse && isInUse(port))
            return $"Another program on this computer is already using port {port}. Choose a different number.";
        return null;
    }

    /// <summary>The first port from <paramref name="start"/> upward that is free, or null.</summary>
    internal static int? FirstFree(int start, Func<int, bool> isInUse, int range = ScanRange)
    {
        for (var port = start; port < start + range && port <= 65535; port++)
        {
            if (!isInUse(port)) return port;
        }
        return null;
    }

    /// <summary>
    /// Decide the port at startup. Pure: every side effect (probing the machine, asking the
    /// person) is passed in, so the whole decision table is testable.
    /// </summary>
    /// <param name="supplied">From <see cref="SuppliedPort"/>.</param>
    /// <param name="saved">The port saved by an earlier run, if any.</param>
    /// <param name="interactive">Whether there is a person at a desktop to ask.</param>
    /// <param name="isInUse">Whether another program holds a port.</param>
    /// <param name="ask">Shows the dialog; returns the chosen port, or null if they quit.</param>
    internal static PortDecision Decide(
        (string Text, string Source)? supplied,
        int? saved,
        bool interactive,
        Func<int, bool> isInUse,
        Func<PortPrompt, int?> ask)
    {
        string? rejectedSupplied = null;
        if (supplied is { } s)
        {
            var port = ParsePort(s.Text);
            if (port is { } p)
            {
                // An administrator said which port. Use it, save it, never ask. If it is busy the
                // server will fail to bind and say so; second-guessing an explicit choice here is
                // exactly the silent drift this replaces.
                var busy = isInUse(p) ? " It looks like another program is using it right now, so the server may not be able to start." : "";
                return new PortDecision(p, Save: p != saved, $"Using port {p} from {s.Source}.{busy}");
            }
            rejectedSupplied = $"Ignoring {s.Source} value '{s.Text}': a port is a whole number from 1 to 65535. ";
        }

        if (saved is { } savedPort)
        {
            if (!isInUse(savedPort))
                return new PortDecision(savedPort, Save: false, $"{rejectedSupplied}Using saved port {savedPort}.");

            if (!interactive)
            {
                return new PortDecision(null, Save: false,
                    $"{rejectedSupplied}Saved port {savedPort} is in use by another program. Weir does not move to a different "
                    + "port on its own, because that would break every bookmark and link to it, and there is nobody at a "
                    + $"desktop to ask. Free port {savedPort}, or start Weir with --port <number> (or set {PortEnvironmentVariable}) "
                    + "to choose another.");
            }

            var suggested = FirstFree(savedPort + 1, isInUse);
            var chosen = ask(new PortPrompt(PortPromptReason.SavedPortBusy, savedPort, CurrentPortInUse: true, suggested));
            return chosen is { } c
                ? new PortDecision(c, Save: c != savedPort, $"{rejectedSupplied}Saved port {savedPort} was in use; the user chose {c}.")
                : new PortDecision(null, Save: false, $"{rejectedSupplied}Saved port {savedPort} was in use and the user quit without choosing another.");
        }

        // First run: nothing supplied (or it was unusable) and nothing saved.
        var defaultBusy = isInUse(DefaultPort);
        if (!interactive)
        {
            var fallback = defaultBusy ? FirstFree(DefaultPort + 1, isInUse) : DefaultPort;
            if (fallback is null)
            {
                return new PortDecision(null, Save: false,
                    $"{rejectedSupplied}No interactive desktop to ask, and ports {DefaultPort}-{DefaultPort + ScanRange - 1} are all in use. "
                    + $"Start Weir with --port <number> (or set {PortEnvironmentVariable}) to choose one.");
            }
            var why = defaultBusy
                ? $"the default port {DefaultPort} is in use, so Weir chose {fallback}, the first free port above it"
                : $"using the default port {DefaultPort}";
            return new PortDecision(fallback, Save: true,
                $"{rejectedSupplied}First run with no interactive desktop to ask: {why}. Saved; Weir will use port {fallback} from now on. "
                + $"To choose a different port, start Weir with --port <number> or set {PortEnvironmentVariable}.");
        }

        var firstChoice = ask(new PortPrompt(
            PortPromptReason.FirstRun,
            DefaultPort,
            CurrentPortInUse: defaultBusy,
            defaultBusy ? FirstFree(DefaultPort + 1, isInUse) : DefaultPort));
        return firstChoice is { } f
            ? new PortDecision(f, Save: true, $"{rejectedSupplied}First run: the user chose port {f}.")
            : new PortDecision(null, Save: false, $"{rejectedSupplied}First run: the user quit the port dialog without choosing.");
    }

    // -- Persistence ----------------------------------------------------------

    internal static int? LoadSaved(string runtimeHome)
    {
        var path = Path.Combine(runtimeHome, SavedPortFileName);
        try
        {
            return File.Exists(path) ? ParsePort(File.ReadAllText(path)) : null;
        }
        catch (Exception ex)
        {
            Program.AppendFallbackLog($"{SavedPortFileName} could not be read ({ex.Message}); treating the port as not yet chosen.");
            return null;
        }
    }

    internal static void Save(string runtimeHome, int port)
    {
        Directory.CreateDirectory(runtimeHome);
        var path = Path.Combine(runtimeHome, SavedPortFileName);
        // Whole-then-rename, as UpdateSettings.Save does: a torn write would read as "never
        // chosen" and put the first-run dialog in front of someone who already answered it.
        var tmp = Path.Combine(runtimeHome, $".port.{Guid.NewGuid():n}.tmp");
        try
        {
            File.WriteAllText(tmp, port.ToString(CultureInfo.InvariantCulture));
            File.Move(tmp, path, overwrite: true);
        }
        catch
        {
            if (File.Exists(tmp)) File.Delete(tmp);
            throw;
        }
    }

    // -- The machine ----------------------------------------------------------

    /// <summary>
    /// Whether a person can answer a dialog. False for a service, a WinRM or SSH session,
    /// or anything else in session 0 — where a modal dialog would wait forever for nobody.
    /// </summary>
    internal static bool HasInteractiveDesktop()
    {
        try
        {
            return Environment.UserInteractive
                && System.Diagnostics.Process.GetCurrentProcess().SessionId != 0
                && SystemInformation.UserInteractive;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Whether another program already holds <paramref name="port"/>. The server binds every
    /// interface, so this checks the listener table and then tries an exclusive bind on
    /// 0.0.0.0 — a port Windows has reserved (Hyper-V and WSL reserve ranges) fails that too.
    /// </summary>
    internal static bool IsInUse(int port)
    {
        try
        {
            if (IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners().Any(ep => ep.Port == port))
                return true;
        }
        catch { }

        try
        {
            using var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp)
            {
                ExclusiveAddressUse = true,
            };
            socket.Bind(new IPEndPoint(IPAddress.Any, port));
            return false;
        }
        catch (SocketException)
        {
            return true;
        }
    }
}
