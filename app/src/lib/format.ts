/**
 * Pure display formatters.
 *
 * Every formatter tolerates messy input — the v3 schema mixes
 * int64 / float64 / null / empty-string across states (e.g.
 * `assessed_value` is float64 on AR but int64 on MT) — and returns
 * `null` when there is genuinely nothing to show. Callers render a
 * `null` as an em-dash.
 *
 * Ported from the v1 app's helpers (app/app.js), which were correct;
 * this is the single typed home for them.
 */

/** Coerce to a finite number, else null. Treats '' / null / undefined as absent. */
function toNum(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Whole-dollar money, e.g. 299935 -> "$299,935". */
export function fmtMoney(v: unknown): string | null {
  const n = toNum(v);
  if (n === null) return null;
  return '$' + Math.round(n).toLocaleString('en-US');
}

/** Acreage, e.g. 285.79 -> "285.79 ac". */
export function fmtAcres(v: unknown): string | null {
  const n = toNum(v);
  return n === null ? null : `${n.toFixed(2)} ac`;
}

/** Height in metres with a feet conversion, e.g. 79.248 -> "79.2 m (260 ft)". */
export function fmtMeters(v: unknown): string | null {
  const n = toNum(v);
  if (n === null) return null;
  const ft = Math.round(n * 3.28084);
  return `${n.toFixed(1)} m (${ft.toLocaleString('en-US')} ft)`;
}

/** Lat/lon pair, e.g. "33.00588, -91.31267". Null unless both are numeric. */
export function fmtLatLng(lat: unknown, lon: unknown): string | null {
  const la = toNum(lat);
  const lo = toNum(lon);
  if (la === null || lo === null) return null;
  return `${la.toFixed(5)}, ${lo.toFixed(5)}`;
}

/** Integer with thousands separators, e.g. 2116976 -> "2,116,976". */
export function fmtInt(v: unknown): string | null {
  const n = toNum(v);
  return n === null ? null : Math.round(n).toLocaleString('en-US');
}

/** Year built — a float64 like 1998.0. Zero / negative means "no data". */
export function fmtYear(v: unknown): string | null {
  const n = toNum(v);
  if (n === null || n <= 0) return null;
  return String(Math.round(n));
}

/** Interestingness score (0–1), e.g. 0.9 -> "0.90". */
export function fmtScore(v: unknown): string | null {
  const n = toNum(v);
  return n === null ? null : n.toFixed(2);
}

/** Generating capacity, e.g. 4.5 -> "4.5 MW". */
export function fmtMw(v: unknown): string | null {
  const n = toNum(v);
  return n === null ? null : `${n.toFixed(1)} MW`;
}

/** A boolean, or a stringified boolean ('True'/'false'), as "Yes"/"No". */
export function fmtBool(v: unknown): string | null {
  if (v === true) return 'Yes';
  if (v === false) return 'No';
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase();
    if (s === 'true') return 'Yes';
    if (s === 'false') return 'No';
  }
  return null;
}

/** Trimmed string, or null when empty / absent. */
export function fmtText(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s === '' ? null : s;
}

/** Join the non-empty parts of a list (e.g. an address), or null if all empty. */
export function joinNonEmpty(parts: unknown[], sep = ', '): string | null {
  const kept = parts
    .map((p) => (p === null || p === undefined ? '' : String(p).trim()))
    .filter((s) => s !== '');
  return kept.length ? kept.join(sep) : null;
}

/** True when a raw property value is something worth displaying. */
export function hasValue(v: unknown): boolean {
  if (v === null || v === undefined) return false;
  if (typeof v === 'string') return v.trim() !== '';
  if (typeof v === 'number') return Number.isFinite(v);
  if (typeof v === 'boolean') return true;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === 'object') return Object.keys(v as object).length > 0;
  return true;
}

