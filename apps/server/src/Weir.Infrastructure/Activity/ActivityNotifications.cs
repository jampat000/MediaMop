using System.Runtime.CompilerServices;
using Microsoft.Data.Sqlite;
using Weir.Core.Activity;
using Weir.Infrastructure.Sqlite;

namespace Weir.Infrastructure.Activity;

/// <summary>
/// Tells live Activity listeners about writes once they commit (Python's <c>after_commit</c> listener in
/// <c>weir.platform.activity.service</c>): the ids a transaction recorded or updated are collected, and
/// after its commit the database's <see cref="ActivityLatestNotifier"/> hears the largest. A rollback, or a
/// transaction that is never reported committed, notifies nobody.
/// </summary>
public static class ActivityNotifications
{
    /// <summary><c>_PENDING_ACTIVITY_IDS_INFO_KEY</c>.</summary>
    private const string PendingKey = "weir_activity_pending_latest_ids";

    private static readonly ConditionalWeakTable<SqliteDatabase, ActivityLatestNotifier> Notifiers = [];
    private static readonly ConditionalWeakTable<SqliteTransaction, PendingIds> PendingByTransaction = [];

    /// <summary>The notifier for one database (Python's process-wide <c>activity_latest_notifier</c>, per server here).</summary>
    public static ActivityLatestNotifier For(SqliteDatabase database)
    {
        ArgumentNullException.ThrowIfNull(database);
        return Notifiers.GetValue(database, _ => new ActivityLatestNotifier());
    }

    /// <summary>Remember <paramref name="id"/> until <paramref name="uow"/> commits.</summary>
    public static void Track(UnitOfWork uow, long id)
    {
        ArgumentNullException.ThrowIfNull(uow);
        if (uow.Items.TryGetValue(PendingKey, out var existing) && existing is PendingIds pending)
        {
            pending.Add(id);
            return;
        }

        pending = new PendingIds();
        pending.Add(id);
        uow.Items[PendingKey] = pending;
        var notifier = For(uow.Database);
        uow.OnCommitted(() => notifier.Notify(pending.Max));
    }

    /// <summary>Remember <paramref name="id"/> until <see cref="TransactionCommitted"/> reports <paramref name="transaction"/> committed.</summary>
    public static void Track(SqliteTransaction transaction, long id)
    {
        ArgumentNullException.ThrowIfNull(transaction);
        PendingByTransaction.GetValue(transaction, _ => new PendingIds()).Add(id);
    }

    /// <summary>Call after committing a raw transaction that may have written Activity.</summary>
    public static void TransactionCommitted(SqliteDatabase database, SqliteTransaction transaction)
    {
        ArgumentNullException.ThrowIfNull(transaction);
        if (PendingByTransaction.TryGetValue(transaction, out var pending))
        {
            PendingByTransaction.Remove(transaction);
            For(database).Notify(pending.Max);
        }
    }

    private sealed class PendingIds
    {
        private readonly Lock _lock = new();
        private long _max = long.MinValue;

        public long Max
        {
            get
            {
                lock (_lock)
                {
                    return _max;
                }
            }
        }

        public void Add(long id)
        {
            lock (_lock)
            {
                _max = Math.Max(_max, id);
            }
        }
    }
}
