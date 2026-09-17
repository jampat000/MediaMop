using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;
using Weir.Core.Jobs;
using Weir.Infrastructure.Jobs;
using Weir.Infrastructure.Sqlite;

namespace Weir.Api.Tests;

/// <summary>The jobs area wired into the real server: crash recovery on start, and workers that leave unported kinds alone.</summary>
public sealed class JobsStartupTests
{
    [Fact]
    public async Task Startup_recovers_a_job_a_killed_server_left_leased_and_removes_its_temp_output()
    {
        string? tempFile = null;
        string? operatorFile = null;
        await using var server = await WeirTestServer.StartAsync(
            [("WEIR_REFINER_WORKER_COUNT", "1")],
            prepareHome: home =>
            {
                var dbPath = Path.Join(home, "data", "weir.sqlite3");
                Directory.CreateDirectory(Path.GetDirectoryName(dbPath)!);
                var database = new SqliteDatabase(dbPath);
                new SchemaMigrator(database).EnsureAtHead();
                var work = Path.Join(home, "refiner", "refiner-movie-work");
                Directory.CreateDirectory(work);
                tempFile = Path.Join(work, "film.refiner.x1y2z3w4.mkv");
                operatorFile = Path.Join(work, "film.mkv");
                File.WriteAllText(tempFile, "half-written");
                File.WriteAllText(operatorFile, "not Weir's");
                using var connection = database.Open();
                using var command = connection.CreateCommand();
                command.CommandText =
                    "INSERT INTO refiner_jobs (dedupe_key, job_kind, payload_json, status, lease_owner, lease_expires_at, attempt_count) " +
                    "VALUES ('crash', 'refiner.file.remux_pass.v1', '{\"media_scope\":\"movie\",\"relative_media_path\":\"Crash.Test.2020/film.mkv\"}', " +
                    "'leased', 'killed-host-1-w0', '2999-01-01 00:00:00+00:00', 1)";
                command.ExecuteNonQuery();
                SqliteConnection.ClearAllPools();
            });

        var report = server.Services.GetRequiredService<JobsStartupRecoveryService>().LastReport;
        Assert.NotNull(report);
        Assert.Equal(1, report.Jobs.RefinerRequeued);
        Assert.Equal(1, report.WorkTempFilesRemoved);
        Assert.False(File.Exists(tempFile));
        Assert.True(File.Exists(operatorFile));

        // The remux handler is not ported yet (#522), so a running .NET worker must leave the row for a backend that can run it.
        await Task.Delay(500);
        var job = Assert.Single(await server.Services.GetRequiredService<RefinerJobStore>().ListAsync());
        Assert.Equal(RefinerJobStatus.Pending, job.Status);
        Assert.Equal(1, job.AttemptCount);
        Assert.Null(job.LeaseOwner);
    }
}
