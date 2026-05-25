/**
 * SQL-literal primitives shared by the FilterSpec registry (`./filters`)
 * and the outer query builders (`./query`).
 *
 * Extracted from `query.ts` so `filters.ts` can use them without
 * importing the FilterState-aware code that depends on the spec
 * registry — keeps the dependency direction one-way.
 */

/** Escape a string as a SQL literal — wraps in single quotes, doubles internal quotes. */
export function sqlString(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

/** Render a finite number as a SQL literal; throw on NaN/Infinity. */
export function sqlNumber(n: number): string {
  if (!Number.isFinite(n)) throw new Error(`non-finite number in a filter: ${n}`);
  return String(n);
}
