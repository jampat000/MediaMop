/**
 * "1 file", "3 files": a count with the noun that agrees with it. Weir's copy never writes "file(s)" — a
 * parenthesised plural makes the reader do the work the sentence should have done.
 *
 * Both forms are passed in rather than derived, because English plurals are not one rule ("entry" /
 * "entries", "day" / "days") and the caller already knows the word.
 */
export function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString()} ${count === 1 ? one : many}`;
}
