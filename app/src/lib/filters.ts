/**
 * SQL-literal primitives shared by the owner-grained `filter-model.ts`.
 *
 * The parcel-grained filter vocabulary that used to live here was retired
 * with the client-side DuckDB parcel filter subsystem (PRD #192); only the
 * literal escapers the live `FilterModel` still imports remain.
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
