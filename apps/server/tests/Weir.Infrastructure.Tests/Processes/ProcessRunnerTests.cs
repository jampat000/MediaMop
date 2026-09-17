using System.ComponentModel;
using System.Diagnostics;
using System.Text;
using Weir.Infrastructure.Processes;

namespace Weir.Infrastructure.Tests.Processes;

/// <summary>The real <see cref="ProcessRunner"/> on this OS's shell: capture, lines, timeouts, cancellation, tree kill.</summary>
public sealed class ProcessRunnerTests
{
    private static readonly ProcessRunner Runner = new();

    private static string[] Shell(string windows, string posix) =>
        OperatingSystem.IsWindows() ? ["cmd.exe", "/d", "/c", windows] : ["/bin/sh", "-c", posix];

    /// <summary>A shell that starts a long-lived child, so killing only the shell would leave the child holding the pipes.</summary>
    private static string[] ShellWithSleepingChild() =>
        Shell("ping -n 60 127.0.0.1 >NUL & echo done", "sleep 60; echo done");

    [Fact]
    public async Task Stdout_stderr_and_exit_code_are_captured()
    {
        var result = await Runner.RunAsync(new ProcessRequest { Argv = Shell("echo out& echo err 1>&2& exit /b 3", "echo out; echo err 1>&2; exit 3") });

        Assert.Equal(3, result.ExitCode);
        Assert.False(result.TimedOut);
        Assert.Equal("out", Encoding.UTF8.GetString(result.Stdout).Trim());
        Assert.Equal("err", Encoding.UTF8.GetString(result.Stderr).Trim());
    }

    [Fact]
    public async Task Arguments_reach_the_child_token_for_token()
    {
        // dotnet itself echoes nothing useful; the shell's own argument handling is the check on POSIX.
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        var result = await Runner.RunAsync(new ProcessRequest { Argv = ["/bin/sh", "-c", "printf '%s|' \"$@\"", "sh", "a b", "'q'", "\"d\"", ""] });

        Assert.Equal("a b|'q'|\"d\"||", Encoding.UTF8.GetString(result.Stdout));
    }

    [Fact]
    public async Task Tail_keeps_only_the_last_bytes()
    {
        var result = await Runner.RunAsync(new ProcessRequest
        {
            Argv = Shell("for /l %i in (1,1,400) do @echo line %i", "i=1; while [ $i -le 400 ]; do echo line $i; i=$((i+1)); done"),
            Stdout = ProcessOutput.Tail,
            TailBytes = 64,
        });

        Assert.Equal(64, result.Stdout.Length);
        Assert.EndsWith("line 400", Encoding.UTF8.GetString(result.Stdout).TrimEnd(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Lines_arrive_split_on_every_newline_style()
    {
        var lines = new List<string>();

        await Runner.RunAsync(new ProcessRequest
        {
            Argv = Shell("echo one& echo two", "printf 'one\\r\\ntwo\\rthree\\nfour'"),
            OnStdoutLine = lines.Add,
        });

        Assert.Equal(OperatingSystem.IsWindows() ? ["one", "two"] : ["one", "two", "three", "four"], lines);
    }

    [Fact]
    public async Task A_timeout_kills_the_whole_tree_and_returns_promptly()
    {
        var stopwatch = Stopwatch.StartNew();

        var result = await Runner.RunAsync(new ProcessRequest { Argv = ShellWithSleepingChild(), Timeout = TimeSpan.FromMilliseconds(500) });

        stopwatch.Stop();
        Assert.Equal(ProcessTimeoutKind.Overall, result.Timeout);
        // The drain allowance after a kill is five seconds; a surviving child holding the pipe would use all of it.
        Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(4), $"took {stopwatch.Elapsed}");
        Assert.DoesNotContain("done", Encoding.UTF8.GetString(result.Stdout), StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_progress_run_that_never_writes_a_line_is_still_stopped_by_the_timer()
    {
        // #539 item 4: Python's progress loop ("for raw in proc.stdout: ...") only checks its timeout as a line
        // arrives, so a process that never writes one - stuck reading its input, for instance - hangs forever.
        // Here the child (ping/sleep, redirected to NUL/dev-null) writes nothing until well after "echo done",
        // which never runs within the timeout; the timeout is still enforced, on the wall-clock timer alone.
        var lines = new List<string>();
        var stopwatch = Stopwatch.StartNew();

        var result = await Runner.RunAsync(new ProcessRequest
        {
            Argv = ShellWithSleepingChild(),
            OnStdoutLine = lines.Add,
            Timeout = TimeSpan.FromMilliseconds(500),
        });

        stopwatch.Stop();
        Assert.Equal(ProcessTimeoutKind.Overall, result.Timeout);
        Assert.Empty(lines);
        Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(4), $"took {stopwatch.Elapsed}");
    }

    [Fact]
    public async Task Cancellation_kills_the_tree_and_throws()
    {
        using var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(500));
        var stopwatch = Stopwatch.StartNew();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Runner.RunAsync(new ProcessRequest { Argv = ShellWithSleepingChild() }, cancel.Token));

        Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(4), $"took {stopwatch.Elapsed}");
    }

    [Fact]
    public async Task A_throwing_line_callback_kills_the_process_and_rethrows()
    {
        var stopwatch = Stopwatch.StartNew();

        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => Runner.RunAsync(new ProcessRequest
        {
            // The line comes from the long-lived process itself. A line the shell echoes before starting its child
            // races the child's creation: under load the tree kill can run before the child exists to be found.
            Argv = Shell("ping -n 60 127.0.0.1", "echo first; exec sleep 60"),
            OnStdoutLine = _ => throw new InvalidOperationException("stop"),
        }));

        Assert.Equal("stop", error.Message);
        Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(4), $"took {stopwatch.Elapsed}");
    }

    [Fact]
    public async Task A_process_that_lingers_after_closing_stdout_is_killed_after_the_grace()
    {
        // The child closes stdout, then keeps running. cmd.exe cannot close its own stdout, so POSIX only.
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        var result = await Runner.RunAsync(new ProcessRequest
        {
            Argv = ["/bin/sh", "-c", "exec 1>&-; sleep 60"],
            OnStdoutLine = _ => { },
            ExitTimeoutAfterStdoutClosed = TimeSpan.FromMilliseconds(300),
            Timeout = TimeSpan.FromSeconds(30),
        });

        Assert.True(result.TimedOut);
    }

    [Fact]
    public async Task A_missing_executable_throws()
    {
        await Assert.ThrowsAsync<Win32Exception>(() => Runner.RunAsync(new ProcessRequest { Argv = ["weir-no-such-tool-" + Guid.NewGuid().ToString("N")] }));
    }
}
