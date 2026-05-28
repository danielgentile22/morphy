/**
 * SQL composition for the DuckDB-WASM filter engine.
 *
 * `composeWhere` turns a FilterState into a SQL WHERE-clause body by
 * iterating `FILTER_SPECS` (defined in `./filters`) and joining each
 * spec's contribution with AND. The output is deterministic — the unit
 * tests assert it byte-for-byte, so a filter-logic regression is caught
 * immediately. String literals are single-quote-escaped; numbers are
 * validated finite — no SQL injection even from the free-text owner
 * search.
 */

import { FILTER_SPECS, type FilterState, sqlNumber, sqlString } from './filters';

/** The DuckDB view/table name the parcels_attr.parquet is registered as. */
export const PARCELS_TABLE = 'parcels';

/**
 * The WHERE-clause body for a filter state — `''` when nothing is
 * filtered. Clauses are AND-ed in FILTER_SPECS order so the output is stable.
 */
export function composeWhere(f: FilterState): string {
  const clauses: string[] = [];
  for (const spec of FILTER_SPECS) {
    const fragment = spec.toSQL(f);
    if (fragment !== null) clauses.push(fragment);
  }
  return clauses.join(' AND ');
}

function whereSuffix(where: string): string {
  return where ? ` WHERE ${where}` : '';
}

/** `SELECT count(*) …` — the live filter count. */
export function countQuery(where: string): string {
  return `SELECT count(*)::INTEGER AS n FROM ${PARCELS_TABLE}${whereSuffix(where)}`;
}

/**
 * Matching parcel ids, capped — the map fades non-matches by id.
 * parcels_attr.parquet is pre-sorted by interestingness_score descending,
 * so a plain LIMIT already returns the top-N matches; an ORDER BY here
 * would re-sort millions of rows for nothing.
 */
export function idQuery(where: string, limit: number): string {
  return `SELECT parcel_id FROM ${PARCELS_TABLE}${whereSuffix(where)} LIMIT ${sqlNumber(limit)}`;
}

/** Owner-name autocomplete — distinct owner clusters matching a term. */
export function ownerSearchQuery(term: string, limit = 10): string {
  const like = sqlString(`%${term.toLowerCase().replace(/[%_]/g, (c) => `\\${c}`)}%`);
  return (
    `SELECT owner_name, owner_cluster_id, owner_cluster_size ` +
    `FROM ${PARCELS_TABLE} ` +
    `WHERE owner_name_norm ILIKE ${like} ESCAPE '\\' ` +
    `QUALIFY row_number() OVER (PARTITION BY owner_cluster_id ORDER BY interestingness_score DESC) = 1 ` +
    `ORDER BY owner_cluster_size DESC LIMIT ${sqlNumber(limit)}`
  );
}

/** A single parcel's full attribute row, by exact parcel id. */
export function parcelRowQuery(parcelId: string): string {
  return `SELECT * FROM ${PARCELS_TABLE} WHERE parcel_id = ${sqlString(parcelId)} LIMIT 1`;
}
