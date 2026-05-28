import { describe, it, expect } from 'vitest';
import { emptyFilters, type FilterState } from '../../src/lib/filters';
import {
  composeWhere,
  countQuery,
  idQuery,
  ownerSearchQuery,
  parcelRowQuery,
} from '../../src/lib/query';
import { sqlString } from '../../src/lib/query-sql';

function filters(overrides: Partial<FilterState>): FilterState {
  return { ...emptyFilters(), ...overrides };
}

describe('sqlString', () => {
  it('wraps and escapes single quotes', () => {
    expect(sqlString('llc')).toBe("'llc'");
    expect(sqlString("O'BRIEN FARMS")).toBe("'O''BRIEN FARMS'");
  });
});

describe('composeWhere', () => {
  it('is empty for an unconstrained filter state', () => {
    expect(composeWhere(emptyFilters())).toBe('');
  });

  it('builds an IN clause for a single categorical value', () => {
    expect(composeWhere(filters({ ownerKind: ['llc'] }))).toBe("owner_kind IN ('llc')");
  });

  it('builds an IN clause for multiple values', () => {
    expect(composeWhere(filters({ distressTier: ['distressed', 'at-risk'] }))).toBe(
      "distress_tier IN ('distressed', 'at-risk')",
    );
  });

  it('emits boolean columns bare', () => {
    expect(composeWhere(filters({ hasTower: true }))).toBe('has_tower');
    expect(composeWhere(filters({ inOz: true, persistentPoverty: true }))).toBe(
      'in_oz AND persistent_poverty',
    );
  });

  it('emits threshold and range clauses', () => {
    expect(composeWhere(filters({ scoreMin: 0.5 }))).toBe('interestingness_score >= 0.5');
    expect(composeWhere(filters({ clusterSizeMin: 5 }))).toBe('owner_cluster_size >= 5');
    expect(composeWhere(filters({ assessedValue: [1000, 50000] }))).toBe(
      'assessed_value BETWEEN 1000 AND 50000',
    );
    expect(composeWhere(filters({ acreage: [10, 500] }))).toBe('acreage BETWEEN 10 AND 500');
  });

  it('ignores no-op sentinel values', () => {
    // scoreMin 0 and clusterSizeMin 1 mean "no constraint".
    expect(composeWhere(filters({ scoreMin: 0, clusterSizeMin: 1 }))).toBe('');
  });

  it('escapes the owner-cluster id', () => {
    expect(composeWhere(filters({ ownerClusterId: "ab'cd" }))).toBe(
      "owner_cluster_id = 'ab''cd'",
    );
  });

  it('AND-joins a compound filter in a fixed order', () => {
    const where = composeWhere(
      filters({
        ownerKind: ['llc'],
        distressTier: ['distressed'],
        hasTower: true,
        scoreMin: 0.7,
      }),
    );
    expect(where).toBe(
      "owner_kind IN ('llc') AND distress_tier IN ('distressed') AND " +
        'has_tower AND interestingness_score >= 0.7',
    );
  });

  it('throws rather than emit a non-finite number', () => {
    expect(() => composeWhere(filters({ assessedValue: [NaN, 1] }))).toThrow();
    expect(() => composeWhere(filters({ scoreMin: Infinity }))).toThrow();
  });
});

describe('query builders', () => {
  it('countQuery with and without a WHERE', () => {
    expect(countQuery('')).toBe('SELECT count(*)::INTEGER AS n FROM parcels');
    expect(countQuery('has_tower')).toBe(
      'SELECT count(*)::INTEGER AS n FROM parcels WHERE has_tower',
    );
  });

  it('idQuery selects ids with a cap (no ORDER BY — the parquet is pre-sorted)', () => {
    expect(idQuery('has_tower', 5000)).toBe(
      'SELECT parcel_id FROM parcels WHERE has_tower LIMIT 5000',
    );
  });

  it('ownerSearchQuery builds an escaped ILIKE', () => {
    const sql = ownerSearchQuery('Smith');
    expect(sql).toContain("ILIKE '%smith%'");
    expect(sql).toContain('owner_name_norm');
    expect(sql).toContain('LIMIT 10');
  });

  it('parcelRowQuery selects one row by id', () => {
    expect(parcelRowQuery('0001-05431-0000')).toBe(
      "SELECT * FROM parcels WHERE parcel_id = '0001-05431-0000' LIMIT 1",
    );
  });
});
