/**
 * facets.json — distinct categorical values + counts and numeric ranges,
 * precomputed by scripts/preprocess/facets.py. The filter controls render
 * from this without a DuckDB round-trip.
 */

export interface FacetValue {
  value: string;
  count: number;
}

export interface NumericRange {
  min: number;
  max: number;
}

export interface FacetData {
  total: number;
  /** column name -> value/count pairs, descending by count. */
  categorical: Record<string, FacetValue[]>;
  /** column name -> {min, max}. */
  numeric: Record<string, NumericRange>;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function parseFacets(raw: unknown): FacetData {
  if (!isRecord(raw)) throw new Error('facets.json: root is not an object');

  const categorical: Record<string, FacetValue[]> = {};
  if (isRecord(raw.categorical)) {
    for (const [key, list] of Object.entries(raw.categorical)) {
      if (!Array.isArray(list)) continue;
      categorical[key] = list
        .filter(isRecord)
        .map((v) => ({ value: String(v.value ?? ''), count: Number(v.count) || 0 }))
        .filter((v) => v.value !== '');
    }
  }

  const numeric: Record<string, NumericRange> = {};
  if (isRecord(raw.numeric)) {
    for (const [key, range] of Object.entries(raw.numeric)) {
      if (isRecord(range) && typeof range.min === 'number' && typeof range.max === 'number') {
        numeric[key] = { min: range.min, max: range.max };
      }
    }
  }

  return {
    total: typeof raw.total === 'number' ? raw.total : 0,
    categorical,
    numeric,
  };
}

/** Categorical values for a column (empty if the column has no facet). */
export function facetValues(facets: FacetData, column: string): FacetValue[] {
  return facets.categorical[column] ?? [];
}

/** Numeric range for a column, or null if it has no facet. */
export function facetRange(facets: FacetData, column: string): NumericRange | null {
  return facets.numeric[column] ?? null;
}
