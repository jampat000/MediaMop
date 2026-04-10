/** Human-readable schedule interval for Refiner runtime visibility UI. */

export function formatScheduleIntervalSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return String(seconds);
  }
  if (seconds >= 3600 && seconds % 3600 === 0) {
    const h = seconds / 3600;
    return `${h} h (${seconds} s)`;
  }
  if (seconds >= 60 && seconds % 60 === 0) {
    const m = seconds / 60;
    return `${m} min (${seconds} s)`;
  }
  return `${seconds} s`;
}
