using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Weir.Infrastructure.Scheduling;

namespace Weir.Infrastructure.Tests.Scheduling;

/// <summary>The periodic loop the Python lifespan's asyncio tasks run, and its host.</summary>
public sealed class PeriodicTaskTests
{
    [Fact]
    public async Task A_task_that_runs_at_start_runs_straight_away_then_waits_the_interval()
    {
        var task = new CountingTask(runAtStart: true, interval: TimeSpan.FromHours(1));
        using var stop = new CancellationTokenSource();
        var loop = PeriodicTaskRunner.RunAsync(task, TimeProvider.System, NullLogger.Instance, stop.Token);

        await WaitUntilAsync(() => task.Calls >= 1);
        await Task.Delay(200);
        Assert.Equal(1, task.Calls);

        await stop.CancelAsync();
        await loop.WaitAsync(TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task A_task_that_does_not_run_at_start_waits_one_interval_first()
    {
        // auth-session-cleanup: the first cleanup is an interval after start; startup has just cleaned up.
        var task = new CountingTask(runAtStart: false, interval: TimeSpan.FromMilliseconds(600));
        using var stop = new CancellationTokenSource();
        var loop = PeriodicTaskRunner.RunAsync(task, TimeProvider.System, NullLogger.Instance, stop.Token);

        await Task.Delay(150);
        Assert.Equal(0, task.Calls);
        await WaitUntilAsync(() => task.Calls >= 1);

        await stop.CancelAsync();
        await loop.WaitAsync(TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task A_failed_run_is_logged_and_retried_after_the_cooldown()
    {
        var task = new CountingTask(runAtStart: true, interval: TimeSpan.FromHours(1), cooldown: TimeSpan.FromMilliseconds(20), failFirst: true);
        var logger = new ListLogger();
        using var stop = new CancellationTokenSource();
        var loop = PeriodicTaskRunner.RunAsync(task, TimeProvider.System, logger, stop.Token);

        await WaitUntilAsync(() => task.Calls >= 2);
        Assert.Equal(["counting tick failed"], logger.Errors);

        await stop.CancelAsync();
        await loop.WaitAsync(TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task The_host_runs_every_registered_task_once_however_often_it_is_added()
    {
        var first = new CountingTask(runAtStart: true, interval: TimeSpan.FromHours(1));
        var second = new CountingTask(runAtStart: true, interval: TimeSpan.FromHours(1));
        var services = new ServiceCollection()
            .AddLogging()
            .AddSingleton(TimeProvider.System)
            .AddSingleton<IPeriodicTask>(first)
            .AddSingleton<IPeriodicTask>(second);
        services.AddWeirPeriodicTasks();
        services.AddWeirPeriodicTasks();
        await using var provider = services.BuildServiceProvider();
        var hosted = Assert.Single(provider.GetServices<IHostedService>());

        await hosted.StartAsync(CancellationToken.None);
        await WaitUntilAsync(() => first.Calls >= 1 && second.Calls >= 1);
        await hosted.StopAsync(CancellationToken.None);
    }

    private static async Task WaitUntilAsync(Func<bool> condition)
    {
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (!condition())
        {
            if (DateTime.UtcNow > deadline)
            {
                throw new TimeoutException();
            }

            await Task.Delay(10);
        }
    }

    private sealed class CountingTask(bool runAtStart, TimeSpan interval, TimeSpan? cooldown = null, bool failFirst = false) : IPeriodicTask
    {
        private int _calls;

        public int Calls => _calls;

        public string Name => "counting";

        public TimeSpan Interval => interval;

        public bool RunAtStart => runAtStart;

        public TimeSpan? FailureCooldown => cooldown;

        public string FailureMessage => "counting tick failed";

        public Task RunOnceAsync(CancellationToken cancellationToken)
        {
            var call = Interlocked.Increment(ref _calls);
            return failFirst && call == 1 ? throw new InvalidOperationException("boom") : Task.CompletedTask;
        }
    }

    private sealed class ListLogger : ILogger
    {
        public List<string> Errors { get; } = [];

        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (logLevel == LogLevel.Error)
            {
                lock (Errors)
                {
                    Errors.Add(formatter(state, exception));
                }
            }
        }
    }
}
