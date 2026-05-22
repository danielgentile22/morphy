/**
 * SQL composition for the DuckDB-WASM filter engine.
 *
 * `composeWhere` turns a FilterState into a SQL WHERE-clause body. Pure
 * and deterministic — the unit tests assert its output byte-for-byte, so
 * a filter-logic regression is caught immediately. String literals are
 * single-quote-escaped; numbers are validated finite — no SQL injection
 * even from the free-text owner search.
 */

import type { FilterState } from './filters';

/** The DuckDB view/table name the parcels_attr.parquet is registered as. */
export const PARCELS_TABLE = 'parcels';

/** Escape a string as a SQL literal. */
export function sqlString(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

function sqlNumber(n: number): string {
  if (!Number.isFinite(n)) throw new Error(`non-finite number in a filter: ${n}`);
  return String(n);
}

function inClause(column: string, values: string[]): string {
  return `${column} IN (${values.map(sqlString).join(', ')})`;
}

/**
 * The WHERE-clause body for a filter state — `''` when nothing is
 * filtered. Clauses are AND-ed in a fixed order so the output is stable.
 */
export function composeWhere(f: FilterState): string {
  const clauses: string[] = [];

  if (f.ownerKind.length) clauses.push(inClause('owner_kind', f.ownerKind));
  if (f.distressTier.length) clauses.push(inClause('distress_tier', f.distressTier));
  if (f.landUse.length) clauses.push(inClause('land_use_desc', f.landUse));
  if (f.countyFips.length) clauses.push(inClause('county_fips', f.countyFips));

  if (f.hasTower) clauses.push('has_tower');
  if (f.hasSolar) clauses.push('has_solar');
  if (f.hasBillboard) clauses.push('has_billboard');
  if (f.inOz) clauses.push('in_oz');
  if (f.inQct) clauses.push('in_qct');
  if (f.persistentPoverty) clauses.push('persistent_poverty');

  if (f.scoreMin > 0) {
    clauses.push(`interestingness_score >= ${sqlNumber(f.scoreMin)}`);
  }
  if (f.clusterSizeMin > 1) {
    clauses.push(`owner_cluster_size >= ${sqlNumber(f.clusterSizeMin)}`);
  }
  if (f.assessedValue) {
    clauses.push(
      `assessed_value BETWEEN ${sqlNumber(f.assessedValue[0])} ` +
        `AND ${sqlNumber(f.assessedValue[1])}`,
    );
  }
  if (f.acreage) {
    clauses.push(`acreage BETWEEN ${sqlNumber(f.acreage[0])} AND ${sqlNumber(f.acreage[1])}`);
  }
  if (f.ownerClusterId) {
    clauses.push(`owner_cluster_id = ${sqlString(f.ownerClusterId)}`);
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
