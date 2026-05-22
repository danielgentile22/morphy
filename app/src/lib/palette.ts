/**
 * Colour + label tables for data encoding.
 *
 * The Wong (2011) colourblind-safe qualitative palette is the source of
 * every data hue (carried over from the v1 app). CSS chrome colours
 * live in src/app.css; this module is for values consumed by MapLibre
 * paint expressions, the legend, and the detail panels.
 */

/** Wong (2011) colourblind-safe qualitative palette. */
export const WONG = {
  black: '#000000',
  orange: '#e69f00',
  skyBlue: '#56b4e9',
  bluishGreen: '#009e73',
  yellow: '#f0e442',
  blue: '#0072b2',
  vermillion: '#d55e00',
  reddishPurple: '#cc79a7',
} as const;

// ── Distress tier (ARC economic-status tiers, worst → best) ──────────────

export const DISTRESS_TIERS = [
  'distressed',
  'at-risk',
  'transitional',
  'competitive',
  'attainment',
] as const;
export type DistressTier = (typeof DISTRESS_TIERS)[number];

const DISTRESS_TIER_COLOR: Record<string, string> = {
  distressed: WONG.vermillion,
  'at-risk': WONG.orange,
  transitional: WONG.yellow,
  competitive: WONG.skyBlue,
  attainment: WONG.bluishGreen,
};
const DISTRESS_TIER_LABEL: Record<string, string> = {
  distressed: 'Distressed',
  'at-risk': 'At-risk',
  transitional: 'Transitional',
  competitive: 'Competitive',
  attainment: 'Attainment',
};

const NEUTRAL = '#9aa0aa';

export function distressTierColor(tier: unknown): string {
  return DISTRESS_TIER_COLOR[String(tier)] ?? NEUTRAL;
}
export function distressTierLabel(tier: unknown): string {
  const t = String(tier ?? '').trim();
  return DISTRESS_TIER_LABEL[t] ?? (t || 'Unknown');
}

// ── Distress overlay types (census-tract polygons) ───────────────────────

const OVERLAY_TYPE_COLOR: Record<string, string> = {
  opportunity_zone: WONG.blue,
  qct: WONG.skyBlue,
};
const OVERLAY_TYPE_LABEL: Record<string, string> = {
  opportunity_zone: 'Opportunity Zone',
  qct: 'Qualified Census Tract',
  persistent_poverty: 'Persistent Poverty',
};

export function overlayTypeColor(t: unknown): string {
  return OVERLAY_TYPE_COLOR[String(t)] ?? NEUTRAL;
}
export function overlayTypeLabel(t: unknown): string {
  const k = String(t ?? '').trim();
  return OVERLAY_TYPE_LABEL[k] ?? (k ? k.replace(/_/g, ' ') : 'Overlay');
}

// ── Owner kind ───────────────────────────────────────────────────────────

const OWNER_KIND_LABEL: Record<string, string> = {
  llc: 'LLC',
  trust: 'Trust',
  partnership: 'Partnership',
  corporation: 'Corporation',
  individual: 'Individual',
  church: 'Church',
  unknown: 'Unknown',
};
export function ownerKindLabel(k: unknown): string {
  const key = String(k ?? '').trim().toLowerCase();
  return OWNER_KIND_LABEL[key] ?? (key ? key.replace(/_/g, ' ') : 'Unknown');
}

// ── Per-layer / per-view base colours ────────────────────────────────────
// Keyed by catalog layer name and view name. The map and legend consult
// this; an unknown layer falls back to NEUTRAL.

export const LAYER_COLORS: Record<string, string> = {
  // base layers
  towers: WONG.black,
  distress_overlays: WONG.blue,
  solar_facilities: WONG.orange,
  // views (toggleable overlays)
  interestingness_top_1000: WONG.vermillion,
  parcels_hosting_infra: WONG.bluishGreen,
  distressed_parcels_hosting_infra: WONG.reddishPurple,
  llc_owned_parcels_with_infra: WONG.yellow,
  towers_with_landowner: WONG.bluishGreen,
};

export function layerColor(name: string): string {
  return LAYER_COLORS[name] ?? NEUTRAL;
}

/** Human-readable names for catalog layers + views. */
const LAYER_LABELS: Record<string, string> = {
  towers: 'Towers',
  distress_overlays: 'Distress overlays (OZ + QCT)',
  solar_facilities: 'Solar facilities',
  interestingness_top_1000: 'Top 1,000 parcels',
  parcels_hosting_infra: 'Parcels hosting infrastructure',
  distressed_parcels_hosting_infra: 'Distressed parcels with infrastructure',
  llc_owned_parcels_with_infra: 'LLC-owned parcels with infrastructure',
  towers_with_landowner: 'Towers with an identified landowner',
};

/** Display label for a layer / view — falls back to a humanised name so a
 *  future catalog entry still renders something sensible. */
export function layerLabel(name: string): string {
  return LAYER_LABELS[name] ?? name.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

// ── Tower marker ─────────────────────────────────────────────────────────
// A self-contained marker icon (dark disc + white tower glyph), rendered
// to a bitmap by MapView and registered with MapLibre via addImage.

export const TOWER_MARKER_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
  <circle cx="14" cy="14" r="11" fill="#212121" stroke="#ffffff" stroke-width="2"/>
  <g fill="none" stroke="#ffffff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
    <path d="M9 20 L14 8 L19 20"/>
    <path d="M11 15 H17"/>
    <path d="M12 12 H16"/>
  </g>
  <circle cx="14" cy="7" r="1.15" fill="#ffffff"/>
</svg>`;
